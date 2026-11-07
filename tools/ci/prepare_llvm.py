"""Prepare compiler artifacts separately from strict-cold browser measurements."""

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shlex
import shutil
import subprocess
import tarfile
import tempfile
import time
import urllib.parse
import urllib.request

from tools.ci.chromium import ROOT


SOURCE_REVISION = '35bd1a85beead3d12dbb8f9a54ebe94aa7e3c724'
SOURCE_SHA256 = '4fe4faf91f10e9679bf392adf810eb1a7f3b3033f7515deeca657d34f3564456'
SOURCE_URL = 'https://github.com/hermeticbuild/hermetic-llvm/archive/' + SOURCE_REVISION + '.tar.gz'
TARGET = '//prebuilt/llvm:for_linux_amd64_musl'
PATCH = ROOT / 'build/llvm-cxx-fdo-training.patch'


def preparation_rc(text):
    lines = []
    for line in text.splitlines():
        tokens = shlex.split(line, comments=True)
        if not tokens:
            lines.append(line)
            continue
        if tokens[0] in ('import', 'try-import'):
            if tokens != ['try-import', '%workspace%/.bazelrc.user']:
                raise ValueError('Unexpected upstream RC import')
            continue
        if len(tokens) > 1 and tokens[1].startswith((
                '--remote_', '--noremote_', '--bes_', '--experimental_remote_downloader')):
            continue
        lines.append(line)
    return '\n'.join(lines) + '\n'


def source_workspace(archive, mode):
    if hashlib.sha256(archive.read_bytes()).hexdigest() != SOURCE_SHA256:
        raise ValueError('Compiler source archive checksum mismatch')
    parent = ROOT / '.compiler-preparation'
    if parent.is_symlink():
        raise ValueError('Compiler preparation root cannot be a symlink')
    parent.mkdir(exist_ok=True)
    marker = parent / '.owned'
    workspace = parent / 'workspace'
    if workspace.exists() or workspace.is_symlink():
        if (workspace.is_symlink() or not marker.is_file()
                or marker.read_text() != SOURCE_REVISION + '\n'):
            raise ValueError('Refusing to replace unowned compiler workspace')
        shutil.rmtree(workspace)
    with tempfile.TemporaryDirectory(prefix='extract-', dir=parent) as temporary:
        with tarfile.open(archive, 'r:gz') as source:
            prefix = 'hermetic-llvm-' + SOURCE_REVISION
            for member in source.getmembers():
                parts = PurePosixPath(member.name).parts
                if not parts or parts[0] != prefix or '..' in parts:
                    raise ValueError('Unexpected compiler source archive path')
            source.extractall(temporary, filter='data')
        (Path(temporary) / prefix).rename(workspace)
    marker.write_text(SOURCE_REVISION + '\n')
    if mode == 'cxx':
        command = ['git', 'apply', '--directory=' + str(workspace.relative_to(ROOT)), str(PATCH)]
        subprocess.run([*command[:2], '--check', *command[2:]], cwd=ROOT, check=True)
        subprocess.run(command, cwd=ROOT, check=True)
    rc = workspace / '.bazelrc'
    rc.write_text(preparation_rc(rc.read_text()))
    if (workspace / '.bazelversion').read_text().strip() != '9.3.0rc2':
        raise ValueError('Unexpected upstream Bazel version')
    return workspace


def compiler_archive(events):
    sets, roots, complete = {}, [], False
    for line in events.read_text().splitlines():
        event = json.loads(line)
        if 'namedSetOfFiles' in event:
            sets[event['id']['namedSet']['id']] = event['namedSetOfFiles']
        if event.get('id', {}).get('targetCompleted', {}).get('label') == TARGET:
            complete = event['completed'].get('success', False)
            roots = [item['id'] for group in event['completed'].get('outputGroup', [])
                     if group['name'] == 'default' for item in group.get('fileSets', [])]
    files, visited = set(), set()
    while roots:
        identifier = roots.pop()
        if identifier in visited:
            continue
        visited.add(identifier)
        group = sets[identifier]
        roots += [item['id'] for item in group.get('fileSets', [])]
        for item in group.get('files', []):
            uri = urllib.parse.urlsplit(item['uri'])
            if uri.scheme != 'file' or uri.netloc:
                raise ValueError('Compiler archive must be downloaded locally')
            path = Path(urllib.parse.unquote(uri.path))
            if path.name.endswith('.tar.zst'):
                files.add(path)
    if not complete or len(files) != 1:
        raise ValueError('Expected one completed compiler archive target')
    return files.pop()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=['baseline', 'cxx'], default='cxx')
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--source-archive', type=Path)
    parser.add_argument('--prepare-only', action='store_true')
    args = parser.parse_args()
    if not args.prepare_only and not os.environ.get('BUILDBUDDY_CI_RUNNER_ABSPATH'):
        parser.error('Compiler build requires a BuildBuddy workflow runner')
    args.directory.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    report = {'scope': 'Compiler preparation, cache-enabled RBE; NOT a cold browser result',
              'source_revision': SOURCE_REVISION, 'source_sha256': SOURCE_SHA256,
              'training': args.mode, 'llvm_version': '23.1.2', 'complete': False,
              'patch_sha256': hashlib.sha256(PATCH.read_bytes()).hexdigest() if args.mode == 'cxx' else None}
    try:
        with tempfile.TemporaryDirectory(prefix='llvm-source-') as temporary:
            archive = args.source_archive or Path(temporary) / 'source.tar.gz'
            if not args.source_archive:
                with urllib.request.urlopen(SOURCE_URL, timeout=120) as response, archive.open('wb') as output:
                    shutil.copyfileobj(response, output)
            workspace = source_workspace(archive, args.mode)
        report['workspace_prepared'] = True
        if args.prepare_only:
            report['build_skipped'] = True
            return
        bazel = os.environ.get('BAZEL', 'bazel')
        version = subprocess.check_output([bazel, '--version'], cwd=workspace, text=True).strip()
        if version != 'bazel 9.3.0rc2':
            raise ValueError('Compiler preparation needs upstream Bazel 9.3.0rc2: ' + version)
        report['bazel_version'] = version
        events = ROOT / '.compiler-preparation/events.json'
        subprocess.run([
            bazel, '--host_jvm_args=-Xmx8g', 'build', '--config=remote', '--config=release',
            '--jobs=128', '--discard_analysis_cache', '--noannounce_rc',
            '--repo_env=BAZEL_MSVC_RUNTIME_VISUAL_STUDIO_EULA=1',
            '--repo_env=BAZEL_WINDOWS_SDK_EULA=1', '--remote_download_outputs=toplevel',
            '--remote_cache=grpcs://formatjs.buildbuddy.io',
            '--remote_executor=grpcs://formatjs.buildbuddy.io',
            '--bes_backend=grpcs://formatjs.buildbuddy.io',
            '--bes_results_url=https://formatjs.buildbuddy.io/invocation/',
            '--build_metadata=REPO_URL=https://github.com/formatjs/chromium.git',
            '--build_metadata=VISIBILITY=PUBLIC', '--remote_instance_name=compiler-training-35bd1a8',
            '--build_event_json_file=' + str(events), '--nobuild_event_json_file_path_conversion', TARGET,
        ], cwd=workspace, check=True)
        source = compiler_archive(events)
        destination = args.directory / ('llvm-23.1.2-linux-amd64-' + args.mode + '.tar.zst')
        shutil.copyfile(source, destination)
        with destination.open('rb') as data:
            digest = hashlib.file_digest(data, 'sha256').hexdigest()
        destination.with_suffix(destination.suffix + '.sha256').write_text(digest + '\n')
        report.update(complete=True, archive=destination.name, archive_sha256=digest)
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        report['elapsed_seconds'] = time.monotonic() - started
        (args.directory / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
