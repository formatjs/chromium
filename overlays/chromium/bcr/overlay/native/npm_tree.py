"""Copy declared npm files into one immutable Bazel tree."""

import json
from pathlib import Path
import shutil
import sys


def main():
    manifest, destination = map(Path, sys.argv[1:])
    destination.mkdir(parents=True, exist_ok=True)
    seen = set()
    parents = set()
    for actual, relative in json.loads(manifest.read_text()):
        path = Path(relative)
        if path.is_absolute() or not path.parts or any(part in ('.', '..') for part in path.parts):
            raise ValueError(f'Unsafe npm path: {relative}')
        if relative in seen:
            raise ValueError(f'Duplicate npm path: {relative}')
        seen.add(relative)
        output = destination / path
        if output.parent not in parents:
            output.parent.mkdir(parents=True, exist_ok=True)
            parents.add(output.parent)
        shutil.copy2(actual, output)


if __name__ == '__main__':
    main()
