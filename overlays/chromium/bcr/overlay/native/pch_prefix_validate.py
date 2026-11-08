"""Reject generated sources whose opening includes no longer match their PCH."""

import json
from pathlib import Path
import sys


def validate(prefix, sources):
    expected = prefix.read_text().splitlines()
    if not expected or any(not line.startswith('#include ') for line in expected):
        raise ValueError('PCH prefix must contain only include directives')
    for source in sources:
        actual = []
        with source.open() as stream:
            for line in stream:
                if line.strip():
                    actual.append(line.rstrip('\n'))
                if len(actual) == len(expected):
                    break
        if actual != expected:
            raise ValueError(f'PCH opening includes changed: {source}')


def main():
    manifest, prefix, output = map(Path, sys.argv[1:])
    validate(prefix, [Path(path) for path in json.loads(manifest.read_text())])
    output.write_text('validated\n')


if __name__ == '__main__':
    main()
