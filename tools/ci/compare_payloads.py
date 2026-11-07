"""Compare cached browser payload bytes, excluding revision stamps."""

import argparse
import gzip
from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
import json
import os
from pathlib import Path
import re
import struct
import tarfile
import tempfile
import urllib.request
import zlib

from tools.ci.buildbuddy_artifacts import (
    COLD_WORKFLOW_PREFIXES, MAX_ARCHIVE_BYTES, api_request, artifact_uris, invocation_id,
)
from tools.ci.chromium import CONFIGURATION, PLATFORMS


def validate_stamp(data, revision, platform):
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:') as archive:
        members = archive.getmembers()
        if len(members) != 1 or members[0].name != 'artifact.json' or not members[0].isfile():
            raise ValueError('Expected one artifact stamp')
        metadata = json.load(archive.extractfile(members[0]))
    expected = {
        'schema_version': 1, 'platform': platform, 'revision': revision,
        'version': CONFIGURATION['version'], 'executable': PLATFORMS[platform]['executable'],
    }
    if metadata != expected:
        raise ValueError('Artifact stamp does not match requested build')


def payload_digest(source, expected_checksum, revision, platform):
    decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
    stamp = bytearray()
    archive_hash, payload_hash = hashlib.sha256(), hashlib.sha256()
    archive_size = payload_size = prefix_size = 0
    while chunk := source.read(1024 * 1024):
        archive_size += len(chunk)
        if archive_size > MAX_ARCHIVE_BYTES:
            raise ValueError('Artifact exceeds size limit')
        archive_hash.update(chunk)
        if decoder.eof:
            payload_hash.update(chunk)
            payload_size += len(chunk)
            continue
        stamp.extend(decoder.decompress(chunk, 65537 - len(stamp)))
        prefix_size += len(chunk) - len(decoder.unused_data)
        if len(stamp) > 65536 or prefix_size > 1024 * 1024:
            raise ValueError('Artifact stamp exceeds size limit')
        if decoder.eof:
            validate_stamp(stamp, revision, platform)
            payload_hash.update(decoder.unused_data)
            payload_size += len(decoder.unused_data)
    if not decoder.eof or not payload_size:
        raise ValueError('Artifact is missing its cached payload')
    if archive_hash.hexdigest() != expected_checksum:
        raise ValueError('Artifact SHA256 mismatch')
    return {'sha256': payload_hash.hexdigest(), 'size_bytes': payload_size}


def pe_summary(data):
    """Report section hashes without changing the payload comparison gate."""
    if len(data) < 64 or data[:2] != b'MZ':
        raise ValueError('Invalid PE DOS header')
    offset = struct.unpack_from('<I', data, 60)[0]
    if offset + 24 > len(data) or data[offset:offset + 4] != b'PE\0\0':
        raise ValueError('Invalid PE header')
    machine, count, timestamp = struct.unpack_from('<HHI', data, offset + 4)
    optional_size = struct.unpack_from('<H', data, offset + 20)[0]
    table = offset + 24 + optional_size
    if count > 96 or table + count * 40 > len(data):
        raise ValueError('Invalid PE section table')
    sections = []
    layouts = []
    for index in range(count):
        start = table + index * 40
        name = data[start:start + 8].rstrip(b'\0').decode('ascii')
        size, position = struct.unpack_from('<II', data, start + 16)
        virtual_size, address = struct.unpack_from('<II', data, start + 8)
        if position + size > len(data):
            raise ValueError('Invalid PE section bounds')
        sections.append({'name': name, 'offset': position, 'size': size,
                         'sha256': hashlib.sha256(memoryview(data)[position:position + size]).hexdigest()})
        layouts.append((address, max(size, virtual_size), position))
    result = {'machine': machine, 'timestamp': timestamp, 'sections': sections}
    optional = offset + 24
    if optional_size >= 168 and struct.unpack_from('<H', data, optional)[0] == 0x20b:
        debug_address, debug_size = struct.unpack_from('<II', data, optional + 112 + 6 * 8)
        for address, size, position in layouts:
            if address <= debug_address < address + size:
                directory = position + debug_address - address
                if debug_size > 4096 or debug_size % 28 or directory + debug_size > len(data):
                    raise ValueError('Invalid PE debug directory')
                for entry in range(directory, directory + debug_size, 28):
                    kind, length, _, pointer = struct.unpack_from('<IIII', data, entry + 12)
                    if kind == 2 and length >= 24 and pointer + length <= len(data) and data[pointer:pointer + 4] == b'RSDS':
                        result['codeview'] = {'guid_hex': data[pointer + 4:pointer + 20].hex(),
                                              'age': struct.unpack_from('<I', data, pointer + 20)[0],
                                              'pdb_path': data[pointer + 24:pointer + length].rstrip(b'\0').decode('utf-8')}
                        digest = hashlib.sha256()
                        digest.update(memoryview(data)[:pointer + 4])
                        digest.update(b'\0' * 16)
                        digest.update(memoryview(data)[pointer + 20:])
                        result['diagnostic_sha256_without_codeview_guid'] = digest.hexdigest()
                break
    return result


def payload_manifest(path, verify_nss=False, diagnose_pdb=False):
    """Inspect the cached gzip member without extracting or executing files."""
    modules = _nss_modules() if verify_nss else {}
    with path.open('rb') as raw:
        prefix = raw.read(1024 * 1024)
        decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
        decoder.decompress(prefix, 65537)
        if not decoder.eof:
            raise ValueError('Artifact stamp exceeds size limit')
        offset = len(prefix) - len(decoder.unused_data)
        raw.seek(offset)
        header = raw.read(10).hex()
        raw.seek(offset)
        digest, size = hashlib.sha256(), 0
        with gzip.GzipFile(fileobj=raw, mode='rb') as source:
            while chunk := source.read(1024 * 1024):
                size += len(chunk)
                if size > 32 * 1024 * 1024 * 1024:
                    raise ValueError('Uncompressed payload exceeds 32 GiB')
                digest.update(chunk)
        raw.seek(offset)
        members, names, checksums, ranges = [], set(), {}, []
        with gzip.GzipFile(fileobj=raw, mode='rb') as source, tarfile.open(fileobj=source, mode='r|') as archive:
            for member in archive:
                if member.name in names:
                    raise ValueError('Duplicate payload member')
                names.add(member.name)
                if len(members) >= 100000:
                    raise ValueError('Payload contains too many members')
                row = {key: getattr(member, key) for key in (
                    'name', 'size', 'mode', 'uid', 'gid', 'mtime', 'uname', 'gname', 'linkname', 'pax_headers')}
                row['type'] = member.type.decode('latin1')
                if member.isfile():
                    with archive.extractfile(member) as content:
                        if diagnose_pdb and member.name == 'bundle/chrome.dll.pdb':
                            from tools.ci.pdb_diagnostics import summarize
                            row['pdb'] = summarize(content, member.size)
                            row['sha256'] = row['pdb']['sha256']
                        elif member.name == 'bundle/chrome.dll':
                            if member.size > 1024 * 1024 * 1024:
                                raise ValueError('PE diagnostic exceeds 1 GiB')
                            data = content.read()
                            row['sha256'] = hashlib.sha256(data).hexdigest()
                            row['pe'] = pe_summary(data)
                        elif verify_nss and member.name in modules:
                            data = content.read(4097)
                            if len(data) > 4096 or len(data) != member.size:
                                raise ValueError('Invalid NSS integrity file size')
                            checksums[member.name] = data
                            ranges.append((member.offset_data, member.size))
                            row['sha256'] = hashlib.sha256(data).hexdigest()
                        else:
                            row['sha256'] = hashlib.file_digest(content, 'sha256').hexdigest()
                members.append(row)
        verification = {}
        if verify_nss:
            from tools.ci.nss_integrity import verify_checksum
            if names.intersection(modules) and set(checksums) != set(modules):
                raise ValueError('Missing NSS integrity files')
            by_name = {member['name']: member for member in members}
            for name, data in checksums.items():
                module = by_name.get(modules[name], {})
                if 'sha256' not in module:
                    raise ValueError('Missing NSS module bytes')
                verification[name] = verify_checksum(data, module['sha256'])
        canonical = digest.hexdigest()
        if ranges:
            # Only verified NSS integrity data may vary.
            raw.seek(offset)
            canonical_hash, position = hashlib.sha256(), 0
            with gzip.GzipFile(fileobj=raw, mode='rb') as source:
                while chunk := source.read(1024 * 1024):
                    normalized = bytearray(chunk)
                    for start, length in ranges:
                        left, right = max(position, start), min(position + len(chunk), start + length)
                        if left < right:
                            normalized[left - position:right - position] = b'\0' * (right - left)
                    canonical_hash.update(normalized)
                    position += len(chunk)
            canonical = canonical_hash.hexdigest()
    return {'tar_sha256': digest.hexdigest(), 'tar_size_bytes': size,
            'gzip_header_hex': header, 'members': members,
            'verified_tar_sha256': canonical, 'nss_integrity': verification}


def _nss_modules():
    from tools.ci.nss_integrity import MODULES
    return MODULES


def verified_contents_match(left, right):
    a, b = left['manifest'], right['manifest']
    return (a['verified_tar_sha256'] == b['verified_tar_sha256']
            and a['tar_size_bytes'] == b['tar_size_bytes']
            and a['nss_integrity'] == b['nss_integrity'])


def build_urls(revision, platforms=PLATFORMS, kind='browser'):
    repository = os.environ.get('GITHUB_REPOSITORY', 'formatjs/chromium')
    request = urllib.request.Request(
        f'https://api.github.com/repos/{repository}/commits/{revision}/status?per_page=100',
        headers={'Authorization': 'Bearer ' + os.environ['GH_TOKEN']})
    with urllib.request.urlopen(request, timeout=60) as response:
        statuses = json.load(response)['statuses']
    by_context = {}
    for status in statuses:
        by_context.setdefault(status['context'], status)
    urls = {}
    prefixes = COLD_WORKFLOW_PREFIXES if kind == 'cold-browser' else ('Chromium ',)
    for platform in platforms:
        status = next((by_context[prefix + platform] for prefix in prefixes
                       if by_context.get(prefix + platform, {}).get('state') == 'success'), {})
        if status.get('state') != 'success':
            raise ValueError('Browser build has not passed: ' + platform)
        urls[platform] = status['target_url']
    return urls


def digest_artifact(url, revision, platform, kind='browser', *, diagnose_members=False, verify_nss=False):
    key = os.environ['BUILDBUDDY_API_KEY']
    with api_request('GetInvocation', {
            'selector': {'invocation_id': invocation_id(url)}, 'include_artifacts': True,
    }, key) as response:
        uris = artifact_uris(json.load(response), revision, platform, kind=kind)
    name = 'chromium-' + platform + '.tar.gz'
    with api_request('GetFile', {'uri': uris[name + '.sha256']}, key) as response:
        expected = response.read(66).decode().strip()
    if not re.fullmatch(r'[0-9a-f]{64}', expected):
        raise ValueError('Invalid artifact checksum')
    with api_request('GetFile', {'uri': uris[name]}, key) as response:
        if not diagnose_members and not verify_nss:
            return payload_digest(response, expected, revision, platform)
        with tempfile.TemporaryDirectory(prefix='chromium-payload-diff-') as temporary:
            path = Path(temporary) / name
            size = 0
            with path.open('wb') as output:
                while chunk := response.read(1024 * 1024):
                    size += len(chunk)
                    if size > MAX_ARCHIVE_BYTES:
                        raise ValueError('Artifact exceeds size limit')
                    output.write(chunk)
            with path.open('rb') as source:
                result = payload_digest(source, expected, revision, platform)
            result['manifest'] = payload_manifest(path, verify_nss=verify_nss, diagnose_pdb=diagnose_members)
            return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', required=True)
    parser.add_argument('--revision', required=True)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--platform', choices=sorted(PLATFORMS))
    parser.add_argument('--revision-kind', choices=['browser', 'cold-browser'], default='browser')
    parser.add_argument('--diagnose-members', action='store_true')
    parser.add_argument('--verify-nss-integrity', action='store_true')
    args = parser.parse_args()
    if any(not re.fullmatch(r'[0-9a-f]{40}', value) for value in (args.baseline, args.revision)):
        parser.error('Expected full source commit SHAs')
    platforms = [args.platform] if args.platform else list(PLATFORMS)
    baseline_key = (args.baseline, 'browser')
    revision_key = (args.revision, args.revision_kind)
    urls_by_build = {key: build_urls(key[0], platforms, key[1]) for key in dict.fromkeys((baseline_key, revision_key))}
    result = {'baseline': args.baseline, 'revision': args.revision,
              'revision_kind': args.revision_kind, 'platforms': {}}
    args.directory.mkdir(parents=True, exist_ok=True)
    # Each optional PDB inspection temporarily stores one multi-gigabyte file.
    with ThreadPoolExecutor(max_workers=1 if args.diagnose_members else 2) as executor:
        futures = {
            (platform, *key): executor.submit(digest_artifact, urls[platform], key[0], platform, key[1],
                                            **({**({'diagnose_members': True} if args.diagnose_members else {}),
                                               **({'verify_nss': True} if args.verify_nss_integrity else {})}))
            for platform in platforms
            for key, urls in urls_by_build.items()
        }
        for platform in platforms:
            baseline = futures[platform, *baseline_key].result()
            current = futures[platform, *revision_key].result()
            result['platforms'][platform] = {
                'baseline': baseline, 'current': current,
                'payload_bytes_match': (baseline['sha256'], baseline['size_bytes'])
                                       == (current['sha256'], current['size_bytes']),
            }
            if args.verify_nss_integrity:
                result['platforms'][platform]['verified_contents_match'] = verified_contents_match(baseline, current)
            byte_match = result['platforms'][platform]['payload_bytes_match']
            print(platform + ': payload bytes ' + ('match' if byte_match else 'changed'), flush=True)
            if args.verify_nss_integrity:
                match = result['platforms'][platform]['verified_contents_match']
                print(platform + ': verified payload contents ' + ('match' if match else 'changed'), flush=True)
            (args.directory / 'payload-comparison.json').write_text(json.dumps(result, indent=2) + '\n')
    gate = 'verified_contents_match' if args.verify_nss_integrity else 'payload_bytes_match'
    if not all(item[gate] for item in result['platforms'].values()):
        raise ValueError('Browser payload bytes changed; inspect code and debug differences')


if __name__ == '__main__':
    main()
