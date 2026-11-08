"""Prepare pinned BOLT and an unstripped compiler; no browser compiler adoption."""

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import urllib.request

from tools.ci.chromium import ROOT
from tools.ci.prepare_llvm import SOURCE_REVISION, SOURCE_SHA256, SOURCE_URL, build_flags, source_workspace


RAW_TARGET = '//toolchain/bootstrap/stage3:llvm_unstripped_for_bolt'
BOLT_TARGET = '@llvm-project//bolt:llvm-bolt'
EXPECTED_STRIPPED_SHA256 = '274f6c48c5de1dad64037c6239fb5310faf1d1844bd1f5bc56feef50b5ee85a4'


def install_target(workspace):
    path = workspace / 'toolchain/bootstrap/stage3/BUILD.bazel'
    text = path.read_text()
    original = 'load("//toolchain/bootstrap:bootstrap_binary.bzl", "bootstrap_binaries")'
    if text.count(original) != 1 or 'llvm_unstripped_for_bolt' in text:
        raise ValueError('Unexpected Stage 3 compiler declaration')
    text = text.replace(original, 'load("//toolchain/bootstrap:bootstrap_binary.bzl", "bootstrap_binaries", "bootstrap_binary")')
    text += '''
bootstrap_binary(
    name = "llvm_unstripped_for_bolt",
    actual = "@llvm-project//llvm:llvm",
    platform = "//platforms:linux_amd64_musl",
    source_backed = True,
    fdo_profile = ":llvm_fdo_profdata",
    symlink = False,
    visibility = ["//visibility:public"],
)
'''
    path.write_text(text)
    return hashlib.sha256(text.encode()).hexdigest()


def digest(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def inspect_compiler(compiler, directory):
    sections = json.loads(subprocess.check_output(
        ['llvm-readobj', '--elf-output-style=JSON', '--sections', str(compiler)],
        executable=compiler, text=True))
    if len(sections) != 1 or sections[0]['FileSummary']['Format'] != 'elf64-x86-64':
        raise ValueError('Unexpected compiler ELF format')
    names = [row['Section']['Type']['Name'] for row in sections[0]['Sections']]
    if 'SHT_SYMTAB' not in names:
        raise ValueError('BOLT compiler input lacks unstripped symbol table')
    stripped = directory / 'compiler-reference.stripped'
    subprocess.run(['llvm-strip', '--strip-all', '-o', str(stripped), str(compiler)],
                   executable=compiler, check=True)
    sha = digest(stripped)
    stripped.unlink()
    if sha != EXPECTED_STRIPPED_SHA256:
        raise ValueError('Unstripped compiler does not reproduce pinned Chromium-trained driver')
    return {'elf_format': 'elf64-x86-64', 'symbol_table_present': True,
            'stripped_driver_sha256': sha, 'original_driver_bytes_match': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--training-inputs', type=Path, required=True)
    parser.add_argument('--source-archive', type=Path)
    parser.add_argument('--prepare-only', action='store_true')
    args = parser.parse_args()
    if not args.prepare_only and not os.environ.get('BUILDBUDDY_CI_RUNNER_ABSPATH'):
        parser.error('BOLT preparation requires a BuildBuddy workflow runner')
    args.directory.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    report = {'scope': 'Cache-enabled RBE tool preparation, NOT a cold browser measurement',
              'source_revision': SOURCE_REVISION, 'source_sha256': SOURCE_SHA256,
              'bolt_applied': False, 'compiler_adopted': False, 'complete': False}
    try:
        with tempfile.TemporaryDirectory(prefix='llvm-bolt-source-') as temporary:
            archive = args.source_archive or Path(temporary) / 'source.tar.gz'
            if not args.source_archive:
                with urllib.request.urlopen(SOURCE_URL, timeout=120) as response, archive.open('wb') as output:
                    shutil.copyfileobj(response, output)
            workspace = source_workspace(archive, 'chromium', args.training_inputs)
        report['stage3_declaration_sha256'] = install_target(workspace)
        report['training_inputs'] = json.loads((workspace / 'toolchain/bootstrap/stage3/chromium_training/provenance.json').read_text())
        if args.prepare_only:
            report['workspace_prepared'] = True
            return
        bazel = os.environ.get('BAZEL', 'bazel')
        version = subprocess.check_output([bazel, '--version'], cwd=workspace, text=True).strip()
        if version != 'bazel 9.3.0rc2':
            raise ValueError('BOLT preparation requires pinned upstream Bazel: ' + version)
        report['bazel_version'] = version
        startup = [bazel, '--host_jvm_args=-Xmx8g']
        flags = build_flags(args.directory / 'events.json') + ['--platforms=//platforms:linux_amd64_musl']
        subprocess.run([*startup, 'build', *flags, RAW_TARGET, BOLT_TARGET], cwd=workspace, check=True)
        query_flags = flags + ['--nodiscard_analysis_cache', '--track_incremental_state', '--keep_state_after_build']
        output = subprocess.check_output([
            *startup, 'cquery', *query_flags, '--output=starlark',
            '--starlark:expr=(str(target.label), [f.path for f in target.files.to_list()])',
            'set(' + RAW_TARGET + ' ' + BOLT_TARGET + ')',
        ], cwd=workspace, text=True)
        rows = [ast.literal_eval(line) for line in output.splitlines()]
        if len(rows) != 2 or any(len(files) != 1 for _, files in rows):
            raise ValueError('Unexpected BOLT preparation artifact inventory')
        artifacts = {}
        for label, files in rows:
            name = 'llvm-unstripped' if label.endswith(':llvm_unstripped_for_bolt') else 'llvm-bolt' if label.endswith('//bolt:llvm-bolt') else None
            path = workspace / files[0]
            if name is None or name in artifacts or not path.is_file() or path.is_symlink():
                raise ValueError('Unexpected BOLT preparation output')
            destination = args.directory / name
            shutil.copyfile(path, destination)
            destination.chmod(0o755)
            artifacts[name] = {'sha256': digest(destination), 'bytes': destination.stat().st_size}
        if set(artifacts) != {'llvm-unstripped', 'llvm-bolt'}:
            raise ValueError('Missing BOLT preparation artifact')
        report['compiler_verification'] = inspect_compiler(args.directory / 'llvm-unstripped', args.directory)
        report['bolt_version'] = subprocess.check_output([str(args.directory / 'llvm-bolt'), '--version'], text=True)
        report.update(complete=True, artifacts=artifacts)
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        report['elapsed_seconds'] = time.monotonic() - started
        (args.directory / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
