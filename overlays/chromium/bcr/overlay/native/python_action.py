# SPDX-License-Identifier: Apache-2.0
"""Stage declared generator inputs; execute with Bazel's Python interpreter."""

import filecmp
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
        directories = set()
        tree_roots = set()
        declared = {}
        merge_directories = set()
        if manifest.get('preserve_node_symlinks', False):
            declared = {logical_path(root, logical): execution_root / actual
                        for actual, logical in manifest['inputs']}
            for path in declared:
                for parent in path.parents:
                    if parent == root:
                        break
                    merge_directories.add(parent)

        def stage_tree(source, destination):
            if destination not in merge_directories:
                destination.symlink_to(source.resolve(), target_is_directory=True)
                tree_roots.add(destination)
                return
            destination.mkdir(parents=True, exist_ok=True)
            for child in source.iterdir():
                output = destination / child.name
                if child.is_dir():
                    stage_tree(child, output)
                elif output in declared:
                    alias = declared[output]
                    if not alias.is_file() or not filecmp.cmp(child, alias, shallow=False):
                        raise ValueError(f'conflicting logical input inside declared directory: {output.relative_to(root)}')
                    # Private copies preserve explicit aliases' source permissions.
                else:
                    output.symlink_to(child.resolve())
                    tree_roots.add(output)

        for actual, logical in manifest['inputs']:
            if logical in staged:
                raise ValueError(f'duplicate logical input: {logical}')
            staged.add(logical)
            destination = logical_path(root, logical)
            if tree_roots and (destination in tree_roots or any(parent in tree_roots for parent in destination.parents)):
                source = execution_root / actual
                if (not source.is_file() or not destination.is_file()
                        or source.stat().st_mode & 0o111 != destination.stat().st_mode & 0o111
                        or not filecmp.cmp(source, destination, shallow=False)):
                    raise ValueError(f'conflicting logical input inside declared directory: {logical}')
                continue
            parent = destination.parent
            if parent not in directories:
                parent.mkdir(parents=True, exist_ok=True)
                directories.add(parent)
            if logical in manifest.get('executable_inputs', manifest.get('symlink_inputs', [])):
                executable = str(execution_root / actual)
                # Keep runtime lookup intact; generators may declare a stable invocation name.
                invocation = manifest.get('executable_names', {}).get(logical, executable)
                destination.write_text(
                    '#!' + sys.executable + ' -I\nimport os, sys\n'
                    'os.execv(' + repr(executable) + ', [' + repr(invocation) + '] + sys.argv[1:])\n')
                destination.chmod(0o755)
            elif (execution_root / actual).is_dir():
                stage_tree(execution_root / actual, destination)
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
        if manifest.get("preserve_node_symlinks", False):
            environment["NODE_OPTIONS"] = "--preserve-symlinks --preserve-symlinks-main"
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
