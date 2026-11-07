#!/usr/bin/env python3
"""Build, package and smoke-test the same Chromium artifact on every target."""

import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import struct
import subprocess
import sys
import tarfile
import tempfile
import time
from urllib.parse import unquote, urlparse


ROOT = Path(__file__).resolve().parents[2]
CONFIGURATION = json.loads((Path(__file__).with_name('platforms.json')).read_text())
PLATFORMS = {item['id']: item for item in CONFIGURATION['platforms']}


def binary_platform(path):
    with path.open('rb') as binary:
        header = binary.read(64)
        if header[:4] == b'\x7fELF' and header[4:6] == b'\x02\x01':
            machine = struct.unpack_from('<H', header, 18)[0]
            return 'linux', {62: 'amd64', 183: 'arm64'}.get(machine)
        if header[:4] == b'\xcf\xfa\xed\xfe':
            machine = struct.unpack_from('<I', header, 4)[0]
            return 'darwin', {0x1000007: 'amd64', 0x100000C: 'arm64'}.get(machine)
        if header[:2] == b'MZ' and len(header) == 64:
            binary.seek(struct.unpack_from('<I', header, 60)[0])
            coff = binary.read(6)
            if coff[:4] == b'PE\0\0' and len(coff) == 6:
                machine = struct.unpack_from('<H', coff, 4)[0]
                return 'windows', {0x8664: 'amd64', 0xAA64: 'arm64'}.get(machine)
    raise ValueError(f'Unsupported executable format: {path}')


def validate_binary(bundle, target):
    executable = bundle / target['executable']
    actual = binary_platform(executable)
    expected = target['os'], target['arch']
    if actual != expected:
        raise ValueError(f'Wrong artifact architecture: expected {expected}, got {actual}')
    return executable


def checksum(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def package_payload(bundle, payload, target, *, compression_level=1):
    bundle = bundle.resolve()
    executable = validate_binary(bundle, target)
    runtime_root = executable.resolve()
    for _ in PurePosixPath(target['executable']).parts:
        runtime_root = runtime_root.parent
    payload.parent.mkdir(parents=True, exist_ok=True)

    def normalize(member):
        relative = PurePosixPath(member.name).relative_to('bundle')
        source = bundle / relative
        sandbox_link = member.issym() and PurePosixPath(member.linkname).is_absolute()
        if sandbox_link:
            # Local sandboxes expose tree input files as absolute symlinks.
            resolved = source.resolve()
            if (not resolved.is_relative_to(runtime_root)
                    or resolved != (runtime_root / relative).resolve()):
                raise ValueError('Archive link outside runtime tree: ' + member.name)
            if not resolved.is_file():
                raise ValueError('Expected runtime file link: ' + member.name)
        if member.islnk() or sandbox_link:
            metadata = source.stat()
            member.type = tarfile.REGTYPE
            member.linkname = ''
            member.size = metadata.st_size
            member.mode = metadata.st_mode
        member.uid = member.gid = member.mtime = 0
        member.uname = member.gname = ''
        member.pax_headers = {}
        member.mode = 0o755 if member.isdir() or member.mode & 0o111 else 0o644
        return member

    with payload.open('wb') as raw, gzip.GzipFile(
            filename='', mode='wb', fileobj=raw, mtime=0, compresslevel=compression_level) as compressed:
        with tarfile.open(fileobj=compressed, mode='w|', format=tarfile.PAX_FORMAT,
                          dereference=False) as output:
            output.add(bundle, arcname='bundle', filter=normalize)
    return payload


def stamp_payload(payload, destination, target, revision):
    if not re.fullmatch(r'[0-9a-f]{40}', revision):
        raise ValueError('Expected a full source commit SHA')
    destination.mkdir(parents=True, exist_ok=True)
    archive = destination / ('chromium-' + target['id'] + '.tar.gz')
    manifest = (json.dumps({
        'schema_version': 1,
        'platform': target['id'],
        'version': CONFIGURATION['version'],
        'revision': revision,
        'executable': target['executable'],
    }, indent=2) + '\n').encode()
    member = tarfile.TarInfo('artifact.json')
    member.size = len(manifest)
    member.mode = 0o644
    # No tar end marker here: the cached payload completes this tar stream.
    prefix = member.tobuf(format=tarfile.PAX_FORMAT) + manifest
    prefix += b'\0' * (-len(manifest) % tarfile.BLOCKSIZE)
    with archive.open('wb') as output:
        with gzip.GzipFile(filename='', mode='wb', fileobj=output, mtime=0, compresslevel=6) as compressed:
            compressed.write(prefix)
        with payload.open('rb') as source:
            shutil.copyfileobj(source, output, length=1024 * 1024)
    archive.with_suffix(archive.suffix + '.sha256').write_text(checksum(archive) + '\n')
    return archive


def package(bundle, destination, target, revision):
    with tempfile.TemporaryDirectory(prefix='chromium-payload-') as temporary:
        payload = package_payload(bundle, Path(temporary) / 'bundle.tar.gz', target)
        return stamp_payload(payload, destination, target, revision)


def grant_windows_sandbox_access(bundle):
    # Match chrome/installer/setup/configure_app_container_sandbox.cc.
    capabilities = (
        'S-1-15-3-1024-3424233489-972189580-2057154623-747635277-1604371224-'
        '316187997-3786583170-1043257646',
        'S-1-15-3-1024-2302894289-466761758-1166120688-1039016420-2430351297-'
        '4240214049-4028510897-3317428798',
    )
    for sid in capabilities:
        subprocess.run(['icacls', str(bundle), '/grant', f'*{sid}:(OI)(CI)(RX)', '/Q'], check=True)


def unpack(artifact, destination, target, revision):
    expected = artifact.with_suffix(artifact.suffix + '.sha256').read_text().strip()
    if not re.fullmatch(r'[0-9a-f]{64}', expected) or checksum(artifact) != expected:
        raise ValueError('Artifact SHA256 mismatch')
    destination.mkdir(parents=True, exist_ok=False)
    with tarfile.open(artifact, 'r:gz') as archive:
        for member in archive.getmembers():
            name = PurePosixPath(member.name)
            if name.is_absolute() or '..' in name.parts or not name.parts:
                raise ValueError(f'Invalid artifact path: {member.name}')
            if name.parts[0] not in ['artifact.json', 'bundle']:
                raise ValueError(f'Unexpected artifact entry: {member.name}')
        archive.extractall(destination, filter='data')
    manifest = json.loads((destination / 'artifact.json').read_text())
    expected_manifest = {
        'schema_version': 1, 'platform': target['id'],
        'version': CONFIGURATION['version'], 'revision': revision,
        'executable': target['executable'],
    }
    if manifest != expected_manifest:
        raise ValueError('Artifact provenance does not match this workflow run')
    bundle = destination / 'bundle'
    validate_binary(bundle, target)
    if target['os'] == 'windows' and platform.system() == 'Windows':
        grant_windows_sandbox_access(bundle)
    return bundle


def cold_build_report(events, elapsed, success, *, expected_output_base=None, output_base_was_fresh=False):
    """Keep cache evidence alongside cold-run timing, including failed runs."""
    metrics = {}
    invocation = None
    output_bases = []
    if events.exists():
        with events.open() as source:
            for line in source:
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if 'started' in event:
                    invocation = event['started'].get('uuid')
                if 'buildMetrics' in event:
                    metrics = event['buildMetrics']
                command = event.get('structuredCommandLine', {})
                if command.get('commandLineLabel') == 'canonical':
                    for section in command.get('sections', []):
                        if section.get('sectionLabel') == 'startup options':
                            output_bases.extend(option.get('optionValue')
                                                for option in section.get('optionList', {}).get('option', [])
                                                if option.get('optionName') == 'output_base')
    output_base_verified = (output_base_was_fresh and expected_output_base is not None
                            and output_bases == [str(expected_output_base)])
    actions = metrics.get('actionSummary', {})
    cached = sum(int(item.get('count', 0)) for item in actions.get('runnerCount', [])
                 if 'cache' in item.get('name', '').lower())
    cached += int(actions.get('actionCacheStatistics', {}).get('hits', 0))
    compiles = sum(int(item.get('actionsExecuted', 0)) for item in actions.get('actionData', [])
                   if item.get('mnemonic') == 'CppCompile')
    return {
        'invocation_id': invocation,
        'elapsed_seconds': elapsed,
        'build_succeeded': success,
        'cold_result_verified': (success and output_base_verified and bool(actions.get('runnerCount'))
                                 and 'actionCacheStatistics' in actions and cached == 0 and compiles > 0),
        'output_base_verified': output_base_verified,
        'output_base_was_absent': output_base_was_fresh,
        'effective_output_base': output_bases[0] if len(output_bases) == 1 else None,
        'cache_state': {
            'bazel_output_state': 'fresh' if output_base_verified else 'unverified',
            'repository_download_cache': 'fresh' if output_base_verified else 'unverified',
            'remote_action_cache_reads': False,
            'disk_action_cache': False,
            'remote_cas': 'shared; not cleared',
        },
        'cached_actions': cached,
        'cpp_compile_actions': compiles,
        'build_metrics': metrics,
    }


def prepare_cold_scratch(parent):
    """Discard only owned scratch state left by a killed hosted cold build."""
    scratch = parent / '.chromium-cold-build'
    marker = scratch / '.owner'
    ownership = 'chromium-ci cold scratch\n'
    if scratch.exists() or scratch.is_symlink():
        if (scratch.is_symlink() or not scratch.is_dir() or marker.is_symlink()
                or not marker.is_file() or marker.read_text() != ownership):
            raise ValueError('Refusing to remove unowned cold scratch')
        if any(child.name != marker.name and (
                child.is_symlink() or not child.is_dir() or not child.name.startswith('chromium-build-'))
               for child in scratch.iterdir()):
            raise ValueError('Unexpected files in cold scratch')
        for child in scratch.iterdir():
            if child.name != marker.name:
                shutil.rmtree(child)
        return scratch
    scratch.mkdir()
    marker.write_text(ownership)
    return scratch


def filesystem_usage(path):
    disk, stat = shutil.disk_usage(path), os.statvfs(path)
    return {'total_bytes': disk.total, 'free_bytes': disk.free,
            'total_inodes': stat.f_files, 'free_inodes': stat.f_favail}


def build(target, destination, revision, hosted=False, cold=False, native_tools=False):
    if cold and not hosted:
        raise ValueError('Cold benchmark requires a BuildBuddy workflow runner')
    if native_tools and target['id'] != 'linux-amd64':
        raise ValueError('Native tool sharing currently requires linux-amd64')
    bazel = [os.environ.get('BAZEL', 'bazel')]
    flags = ['--config=browser']
    if hosted:
        if not os.environ.get('BUILDBUDDY_CI_RUNNER_ABSPATH'):
            raise ValueError('Hosted mode requires a BuildBuddy workflow runner')
        # Retained input trees need heap headroom at 128 active actions.
        bazel.append('--host_jvm_args=-Xmx12g')
        flags.extend(['--config=buildbuddy', '--keep_going', '--noexperimental_remote_discard_merkle_trees'])
        if target['os'] == 'darwin':
            # Bound input downloads for the large framework link.
            flags.extend(['--strategy=CppLink=sandboxed', '--remote_max_connections=8'])
    if native_tools:
        flags.extend(['--define=CHROMIUM_NATIVE_TOOLS=1',
                      '--extra_toolchains=@chromium//native/tool_configuration:native_linux_execution'])
    if target['os'] == 'windows':
        flags.extend([
            '--repo_env=BAZEL_MSVC_RUNTIME_VISUAL_STUDIO_EULA=1',
            '--repo_env=BAZEL_WINDOWS_SDK_EULA=1',
        ])
    if not re.fullmatch(r'[0-9a-f]{40}', revision):
        raise ValueError('Expected a full source commit SHA')
    label = '//tools/ci:' + target['id'] + '_archive'
    started = time.monotonic()
    scratch = prepare_cold_scratch(ROOT.parent) if cold else None
    with tempfile.TemporaryDirectory(prefix='chromium-build-', dir=scratch) as temporary:
        events = Path(temporary) / 'events.json'
        if cold:
            destination.mkdir(parents=True, exist_ok=True)
            flags.append('--profile=' + str(destination / 'cold-profile.json'))
            output_base = Path(temporary) / 'output-base'
            output_base_was_fresh = not output_base.exists()
            if not output_base_was_fresh:
                raise ValueError('Cold output base already exists')
            # Managed RC files may set output_base independently of output_user_root.
            bazel.extend(['--batch', '--output_user_root=' + str(Path(temporary) / 'bazel'),
                          '--output_base=' + str(output_base)])
            flags.extend([
                '--remote_accept_cached=false', '--disk_cache=', '--repo_contents_cache=',
                '--repository_cache=' + str(Path(temporary) / 'repository-cache'),
                '--modify_execution_info=.*=+no-cache',
            ])
        filesystem_before = filesystem_usage(temporary) if cold else None
        if cold:
            print('Cold filesystem before build: ' + json.dumps(filesystem_before), flush=True)
        success = False
        try:
            subprocess.run([
                *bazel, 'build', *flags, '--//tools/ci:revision=' + revision,
                '--build_event_json_file=' + str(events),
                '--nobuild_event_json_file_path_conversion', label,
            ], cwd=ROOT, check=True)
            outputs = artifact_outputs(events, label)
            destination.mkdir(parents=True, exist_ok=True)
            for source in outputs:
                shutil.copyfile(source, destination / source.name)
            success = True
        finally:
            if cold:
                report = cold_build_report(events, time.monotonic() - started, success,
                                           expected_output_base=output_base,
                                           output_base_was_fresh=output_base_was_fresh)
                report['cache_state']['execution_policy'] = 'no-cache; no in-flight action merging'
                report['client_filesystem'] = {
                    'before': filesystem_before, 'after': filesystem_usage(temporary),
                }
                print('Cold filesystem after build: ' + json.dumps(report['client_filesystem']['after']), flush=True)
                destination.mkdir(parents=True, exist_ok=True)
                (destination / 'cold-build.json').write_text(json.dumps(report, indent=2) + '\n')
        if cold and not report['cold_result_verified']:
            raise ValueError('Cold build evidence missing, output base reused, or cached actions detected')
    return destination / ('chromium-' + target['id'] + '.tar.gz')


def artifact_outputs(events, label):
    """Read this target's default output group from the completed build."""
    named_sets = {}
    roots = []
    completed = False
    with events.open() as stream:
        for line in stream:
            event = json.loads(line)
            if 'namedSetOfFiles' in event:
                named_sets[event['id']['namedSet']['id']] = event['namedSetOfFiles']
            if event.get('id', {}).get('targetCompleted', {}).get('label') == label:
                completed = event['completed']['success']
                for group in event['completed'].get('outputGroup', []):
                    if group['name'] == 'default':
                        roots.extend(item['id'] for item in group.get('fileSets', []))
    files = set()
    visited = set()
    while roots:
        identifier = roots.pop()
        if identifier in visited:
            continue
        visited.add(identifier)
        group = named_sets[identifier]
        roots.extend(item['id'] for item in group.get('fileSets', []))
        for item in group.get('files', []):
            uri = urlparse(item['uri'])
            if uri.scheme != 'file' or uri.netloc:
                raise ValueError('Artifact outputs must be downloaded locally')
            files.add(Path(unquote(uri.path)))
    name = 'chromium-' + label.rsplit(':', 1)[1].removesuffix('_archive') + '.tar.gz'
    if not completed or {path.name for path in files} != {name, name + '.sha256'} or len(files) != 2:
        raise ValueError('Build did not produce exactly one archive and checksum')
    return sorted(files)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['matrix', 'build', 'package', 'package-payload', 'stamp-payload', 'smoke'])
    parser.add_argument('--platform', choices=sorted(PLATFORMS))
    parser.add_argument('--revision')
    parser.add_argument('--bundle', type=Path)
    parser.add_argument('--directory', type=Path)
    parser.add_argument('--artifact', type=Path)
    parser.add_argument('--payload', type=Path)
    parser.add_argument('--screenshots', type=Path, help='Rendering evidence directory for smoke tests')
    parser.add_argument('--buildbuddy-hosted', action='store_true',
                        help='Use credentials injected by the BuildBuddy workflow runner')
    parser.add_argument('--cold', action='store_true',
                        help='Benchmark a hosted build with fresh Bazel state and no action-cache reuse')
    parser.add_argument('--native-tools', action='store_true',
                        help='Share matching Linux amd64 native tool configurations')
    args = parser.parse_args()
    if args.cold and (args.command != 'build' or not args.buildbuddy_hosted):
        parser.error('--cold requires build --buildbuddy-hosted')
    if args.native_tools and args.command != 'build':
        parser.error('--native-tools requires build')
    if args.command == 'matrix':
        print(json.dumps({'include': CONFIGURATION['platforms']}, separators=(',', ':')))
        return
    if args.command == 'package-payload':
        if not args.platform or not args.bundle or not args.payload:
            parser.error('--platform, --bundle and --payload are required')
        print(package_payload(args.bundle, args.payload, PLATFORMS[args.platform]))
        return
    if not args.platform or not args.revision or not args.directory:
        parser.error('--platform, --revision and --directory are required')
    target = PLATFORMS[args.platform]
    if args.command == 'stamp-payload':
        if not args.payload:
            parser.error('--payload is required')
        print(stamp_payload(args.payload, args.directory, target, args.revision))
    elif args.command == 'build':
        print(build(target, args.directory, args.revision, hosted=args.buildbuddy_hosted,
                    cold=args.cold, native_tools=args.native_tools))
    elif args.command == 'package':
        if not args.bundle:
            parser.error('--bundle is required')
        print(package(args.bundle, args.directory, target, args.revision))
    else:
        host_os = {'Linux': 'linux', 'Darwin': 'darwin', 'Windows': 'windows'}.get(platform.system())
        host_arch = {'x86_64': 'amd64', 'amd64': 'amd64', 'arm64': 'arm64', 'aarch64': 'arm64'}.get(platform.machine().lower())
        if (host_os, host_arch) != (target['os'], target['arch']):
            raise ValueError(f'Smoke runner does not match {target["id"]}')
        if not args.artifact:
            parser.error('--artifact is required')
        bundle = unpack(args.artifact, args.directory, target, args.revision)
        subprocess.run([
            sys.executable, str(ROOT / 'overlays/chromium/tools/check_browser.py'),
            str(bundle), '--executable', target['executable'],
            '--expected-version', CONFIGURATION['version'],
        ], check=True)
        screenshots = args.screenshots or args.directory.parent / 'rendering'
        subprocess.run([
            sys.executable, '-m', 'tools.ci.check_rendering', str(bundle.resolve()),
            '--executable', target['executable'], '--output', str(screenshots.resolve()),
        ], cwd=ROOT, check=True)


if __name__ == '__main__':
    main()
