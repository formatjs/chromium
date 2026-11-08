"""Capture Chromium inputs and prepare an experimental compiler on BuildBuddy."""

import argparse
import os
from pathlib import Path
import subprocess
import sys

from tools.ci.chromium import ROOT


TARGET = '@chromium//native:llvm_training_inputs'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    args = parser.parse_args()
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
    subprocess.run([sys.executable, '-m', 'tools.ci.prepare_llvm', '--mode', 'chromium',
                    '--training-inputs', str(parents.pop()), '--directory', str(args.directory)],
                   cwd=ROOT, check=True)


if __name__ == '__main__':
    main()
