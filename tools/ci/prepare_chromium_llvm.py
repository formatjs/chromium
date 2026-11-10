"""Capture Chromium inputs and prepare an experimental compiler on BuildBuddy."""

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

from tools.ci.chromium import ROOT
from tools.ci.compiler_training_inputs import install_inputs


TARGET = '@chromium//native:llvm_training_inputs'


def retain_training_inputs(paths, directory):
    """Retain replayable inputs before long compiler preparation."""
    workspace = directory
    stage = workspace / 'toolchain/bootstrap/stage3'
    stage.mkdir(parents=True, exist_ok=False)
    install_inputs(paths[0].parent, workspace)
    destination = stage / 'chromium_training'
    for path in paths:
        if path.suffix in {'.d', '.json'}:
            shutil.copyfile(path, destination / path.name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--bolt-feasibility', action='store_true')
    parser.add_argument('--bolt-relocations', action='store_true')
    parser.add_argument('--bolt-merge-fdata', action='store_true')
    args = parser.parse_args()
    if args.bolt_merge_fdata and not args.bolt_feasibility:
        parser.error('--bolt-merge-fdata requires --bolt-feasibility')
    if args.bolt_relocations and not args.bolt_feasibility:
        parser.error('--bolt-relocations requires --bolt-feasibility')
    if not os.environ.get('BUILDBUDDY_CI_RUNNER_ABSPATH'):
        parser.error('Compiler preparation requires a BuildBuddy workflow runner')
    bazel = os.environ.get('BAZEL', 'bazel')
    startup = [bazel, '--host_jvm_args=-Xmx8g']
    flags = ['--config=browser', '--config=buildbuddy', '--noannounce_rc',
             '--define=CHROMIUM_NATIVE_TOOLS=1', '--define=CHROMIUM_BINDINGS_WORKERS=4',
             '--define=CHROMIUM_COMPILE_PROBE_SCAN=1',
             '--extra_toolchains=@chromium//native/tool_configuration:native_linux_execution']
    subprocess.run([*startup, 'build', *flags, TARGET], cwd=ROOT, check=True)
    query_flags = [*flags, '--nodiscard_analysis_cache', '--track_incremental_state', '--keep_state_after_build']
    files = subprocess.check_output([*startup, 'cquery', *query_flags, '--output=files', TARGET],
                                    cwd=ROOT, text=True).splitlines()
    expected = {'llvm_training_' + name + suffix for name in ['v8', 'content']
                for suffix in ['.ii', '.d', '.json']}
    paths = [ROOT / path for path in files]
    parents = {path.parent for path in paths}
    if len(paths) != len(expected) or len(parents) != 1 or {path.name for path in paths} != expected:
        raise ValueError('Unexpected representative preprocessing outputs')
    subprocess.run([*startup, 'shutdown'], cwd=ROOT, check=True)
    preparation = 'tools.ci.prepare_llvm_bolt' if args.bolt_feasibility else 'tools.ci.prepare_llvm'
    mode = [] if args.bolt_feasibility else ['--mode', 'chromium']
    if args.bolt_relocations:
        mode.append('--relocations')
    if args.bolt_merge_fdata:
        mode.append('--merge-fdata')
    retained = args.directory.with_name(args.directory.name + '-training-inputs')
    retain_training_inputs(paths, retained)
    subprocess.run([sys.executable, '-m', preparation, *mode,
                    '--training-inputs', str(parents.pop()), '--directory', str(args.directory)],
                   cwd=ROOT, check=True)


if __name__ == '__main__':
    main()
