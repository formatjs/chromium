"""Reject changed project imports before exposing an experimental PCH."""

import json
from pathlib import Path
import shutil
import sys


def project_path(path):
    path = path.removeprefix('./')
    if path.startswith('/') or any(part in ('', '.', '..') for part in path.split('/')):
        raise ValueError(f'Unsafe PCH dependency: {path}')
    if path.startswith('bazel-out/'):
        parts = path.split('/', 3)
        if len(parts) != 4 or parts[2] != 'bin':
            raise ValueError(f'Unsupported generated PCH dependency: {path}')
        path = parts[3]
    path = path.removeprefix('external/')
    repository = path.split('/', 1)[0]
    if repository.startswith(('llvm+', 'llvm++')):
        return None
    return path


def validate(dependency, expected):
    # Pinned Linux inputs contain no Make escapes except line continuation.
    text = dependency.replace('\\\n', ' ')
    _, separator, dependencies = text.partition(': ')
    if not separator or any(char in dependencies for char in '\\$:#'):
        raise ValueError('Unsupported PCH depfile syntax')
    actual = {project_path(path) for path in dependencies.split()}
    actual.discard(None)
    expected = set(expected)
    if actual != expected:
        raise ValueError(f'PCH closure changed; missing={sorted(expected - actual)}, added={sorted(actual - expected)}')


def main():
    dependency, manifest, raw, output = map(Path, sys.argv[1:])
    validate(dependency.read_text(), json.loads(manifest.read_text()))
    shutil.copyfile(raw, output)


if __name__ == '__main__':
    main()
