# SPDX-License-Identifier: Apache-2.0
"""Stage declared generator inputs; execute with Bazel's Python interpreter."""

import json
import os
from pathlib import Path, PurePosixPath
import shlex
import shutil
import subprocess
import sys
import tempfile


def logical_path(root, value):
    path = PurePosixPath(value)
    if path.is_absolute() or '..' in path.parts or not path.parts:
        raise ValueError(f'invalid logical path: {value}')
    return root.joinpath(*path.parts)


def run(manifest):
    execution_root = Path.cwd()
    with tempfile.TemporaryDirectory(prefix='chromium-action-') as directory:
        root = Path(directory)
        staged = set()
        for actual, logical in manifest['inputs']:
            if logical in staged:
                raise ValueError(f'duplicate logical input: {logical}')
            staged.add(logical)
            destination = logical_path(root, logical)
            destination.parent.mkdir(parents=True, exist_ok=True)
            if logical in manifest.get('executable_inputs', manifest.get('symlink_inputs', [])):
                executable = str(execution_root / actual)
                # Preserve the tool directory and multicall executable name.
                destination.write_text(
                    '#!' + sys.executable + ' -I\nimport os, sys\n'
                    'os.execv(' + repr(executable) + ', [' + repr(executable) + '] + sys.argv[1:])\n')
                destination.chmod(0o755)
            elif (execution_root / actual).is_dir():
                destination.symlink_to((execution_root / actual).resolve(), target_is_directory=True)
            else:
                shutil.copy2(execution_root / actual, destination)
        build = logical_path(root, manifest['build_dir'])
        build.mkdir(parents=True, exist_ok=True)
        for _, logical in manifest['outputs']:
            logical_path(build, logical).parent.mkdir(parents=True, exist_ok=True)
        response = build / 'action.rsp'
        response.write_text(shlex.join(manifest['response_file_contents']))
        arguments = [arg.replace('{{response_file_name}}', response.name)
                     for arg in manifest['args']]
        if any('{{' in arg or '$LLVM_ROOT' in arg for arg in arguments):
            raise ValueError('unresolved generator argument')
        script = logical_path(root, manifest['script'])
        environment = dict(os.environ, PYTHONPATH=str(script.parent),
                           PYTHONHASHSEED='0', PYTHONNOUSERSITE='1')
        # Child tools resolve their own runfiles.
        for variable in ['RUNFILES_DIR', 'RUNFILES_MANIFEST_FILE']:
            environment.pop(variable, None)
        result = subprocess.run([sys.executable, os.path.relpath(script, build), *arguments],
                                cwd=build, env=environment)
        if result.returncode:
            raise SystemExit(result.returncode)
        for actual, logical in manifest['outputs']:
            source = logical_path(build, logical)
            if not source.is_file():
                raise ValueError(f'generator did not produce {logical}')
            shutil.copyfile(source, execution_root / actual)


if __name__ == '__main__':
    run(json.loads(Path(sys.argv[1]).read_text()))
