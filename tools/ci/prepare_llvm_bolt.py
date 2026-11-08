"""Prepare pinned BOLT and an unstripped compiler; no browser compiler adoption."""

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

from tools.ci.chromium import ROOT
from tools.ci.prepare_llvm import SOURCE_REVISION, SOURCE_SHA256, SOURCE_URL, build_flags, source_workspace
from tools.ci.llvm_bolt_support import RUNTIME_TARGET, install_relocations
from tools.ci.llvm_elf import compare_relinked_compiler


RAW_TARGET = '//toolchain/bootstrap/stage3:llvm_unstripped_for_bolt'
BOLT_TARGET = '@llvm-project//bolt:llvm-bolt'
MERGE_TARGET = '@llvm-project//bolt:merge-fdata'
EXPECTED_STRIPPED_SHA256 = '274f6c48c5de1dad64037c6239fb5310faf1d1844bd1f5bc56feef50b5ee85a4'


COMPILER_ACTION_EXPRESSION = '[(a.mnemonic,a.argv,a.env,[f.path for f in a.outputs.to_list()]) for a in getattr(target,"actions",[]) if a.mnemonic in ["CppCompile","CppHeaderParsing","CppLTOBackend","CppLink","CppLTOIndexing"]]'


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


def compiler_actions(startup, flags, workspace, name):
    path = ROOT / '.compiler-preparation' / (name + '.actions.txt')
    query_flags = flags + ['--nodiscard_analysis_cache', '--track_incremental_state', '--keep_state_after_build']
    log = path.with_suffix('.log')
    with path.open('w') as output, log.open('w') as error:
        process = subprocess.run([*startup, 'cquery', *query_flags, '--output=starlark',
                                  '--starlark:expr=' + COMPILER_ACTION_EXPRESSION,
                                  'deps(labels(actual, ' + RAW_TARGET + '))'],
                                 cwd=workspace, stdout=output, stderr=error)
    if process.returncode or any(line.startswith(('ERROR:', 'Error:')) for line in log.read_text().splitlines()):
        print(log.read_text()[-12000:], file=sys.stderr, flush=True)
        raise ValueError('LLVM compiler action query failed: ' + name)
    result = {}
    for line in path.read_text().splitlines():
        for mnemonic, arguments, environment, outputs in ast.literal_eval(line):
            key = mnemonic, tuple(outputs)
            value = arguments, environment
            if key in result and result[key] != value:
                raise ValueError('Ambiguous LLVM action inventory')
            result[key] = value
    if sum(key[0] == 'CppCompile' for key in result) < 1000:
        raise ValueError('Incomplete LLVM compiler action inventory')
    return result


def verify_relocation_actions(before, after):
    if before.keys() != after.keys():
        raise ValueError('Relocation preparation changes LLVM action inventory')
    changes = []
    for key, (arguments, environment) in before.items():
        updated, updated_environment = after[key]
        if (arguments, environment) == (updated, updated_environment):
            continue
        if (key[0] not in ('CppLink', 'CppLTOIndexing') or updated_environment != environment
                or updated.count('-Wl,--emit-relocs') != 1
                or [value for value in updated if value != '-Wl,--emit-relocs'] != arguments):
            raise ValueError('Relocation preparation changes compiler commands beyond final link metadata')
        changes.append(key[0])
    if changes.count('CppLink') != 1:
        raise ValueError('Expected exactly one changed final LLVM compiler link')
    return {'actions_checked': len(before), 'compile_commands_environment_unchanged': True,
            'changed_link_actions': changes, 'only_added_option': '-Wl,--emit-relocs'}


def copy_runtime(startup, flags, workspace, directory):
    query_flags = flags + ['--nodiscard_analysis_cache', '--track_incremental_state', '--keep_state_after_build']
    output = subprocess.check_output([*startup, 'cquery', *query_flags, '--output=files', RUNTIME_TARGET],
                                     cwd=workspace, text=True).splitlines()
    matches = [workspace / path for path in output if Path(path).name == 'libbolt_rt_instr.a']
    if len(matches) != 1 or not matches[0].is_file() or matches[0].is_symlink():
        raise ValueError('Expected one native BOLT instrumentation runtime archive')
    destination = directory / 'libbolt_rt_instr.a'
    shutil.copyfile(matches[0], destination)
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--training-inputs', type=Path, required=True)
    parser.add_argument('--source-archive', type=Path)
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--relocations', action='store_true')
    parser.add_argument('--merge-fdata', action='store_true')
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
        targets = [RAW_TARGET, BOLT_TARGET] + ([MERGE_TARGET] if args.merge_fdata else [])
        subprocess.run([*startup, 'build', *flags, *targets], cwd=workspace, check=True)
        query_flags = flags + ['--nodiscard_analysis_cache', '--track_incremental_state', '--keep_state_after_build']
        output = subprocess.check_output([
            *startup, 'cquery', *query_flags, '--output=starlark',
            '--starlark:expr=(str(target.label), [f.path for f in target.files.to_list()])',
            'set(' + ' '.join(targets) + ')',
        ], cwd=workspace, text=True)
        rows = [ast.literal_eval(line) for line in output.splitlines()]
        if len(rows) != len(targets) or any(len(files) != 1 for _, files in rows):
            raise ValueError('Unexpected BOLT preparation artifact inventory')
        artifacts = {}
        for label, files in rows:
            if label.endswith(':llvm_unstripped_for_bolt'):
                name = 'llvm-unstripped'
            elif label.endswith('//bolt:llvm-bolt'):
                name = 'llvm-bolt'
            elif label.endswith('//bolt:merge-fdata'):
                name = 'merge-fdata'
            else:
                name = None
            path = workspace / files[0]
            if name is None or name in artifacts or not path.is_file() or path.is_symlink():
                raise ValueError('Unexpected BOLT preparation output')
            destination = args.directory / name
            shutil.copyfile(path, destination)
            destination.chmod(0o755)
            artifacts[name] = {'sha256': digest(destination), 'bytes': destination.stat().st_size}
        expected_artifacts = {'llvm-unstripped', 'llvm-bolt'} | ({'merge-fdata'} if args.merge_fdata else set())
        if set(artifacts) != expected_artifacts:
            raise ValueError('Missing BOLT preparation artifact')
        report['compiler_verification'] = inspect_compiler(args.directory / 'llvm-unstripped', args.directory)
        report['bolt_version'] = subprocess.check_output([str(args.directory / 'llvm-bolt'), '--version'], text=True)
        if args.relocations:
            before = compiler_actions(startup, flags, workspace, 'bolt-baseline')
            report['source_override'] = install_relocations(workspace)
            after = compiler_actions(startup, flags, workspace, 'bolt-relocations')
            report['compiler_action_verification'] = verify_relocation_actions(before, after)
            subprocess.run([*startup, 'build', *flags, RAW_TARGET, RUNTIME_TARGET], cwd=workspace, check=True)
            files = subprocess.check_output([*startup, 'cquery', *query_flags, '--output=files', RAW_TARGET],
                                            cwd=workspace, text=True).splitlines()
            if len(files) != 1 or not (workspace / files[0]).is_file() or (workspace / files[0]).is_symlink():
                raise ValueError('Expected one LLVM compiler with relocation metadata')
            relocated = args.directory / 'llvm-with-relocations'
            shutil.copyfile(workspace / files[0], relocated)
            relocated.chmod(0o755)
            verification = compare_relinked_compiler(args.directory / 'llvm-unstripped', relocated)
            if not verification['symbol_table_present'] or not verification['text_relocation_sections']:
                raise ValueError('BOLT compiler input lacks symbols or text relocations')
            report['relocation_verification'] = verification
            runtime = copy_runtime(startup, flags, workspace, args.directory)
            members = json.loads(subprocess.check_output(
                ['llvm-readobj', '--elf-output-style=JSON', '--file-headers', str(runtime)],
                executable=relocated, text=True))
            if not members or any(row['FileSummary']['Format'] != 'elf64-x86-64' for row in members):
                raise ValueError('BOLT instrumentation runtime contains non-native objects')
            for artifact in [relocated, runtime]:
                artifacts[artifact.name] = {'sha256': digest(artifact), 'bytes': artifact.stat().st_size}
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
