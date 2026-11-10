"""Emit native imports after complete byte, cost and dependency qualification."""

import argparse
import gzip
import hashlib
import json
from pathlib import Path

from tools.ci.compile.shared_prefix_plan import plan_qualified_imports


def read_json(path):
    opener = gzip.open if path.suffix == '.gz' else open
    with opener(path, 'rt') as stream:
        return json.load(stream)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['cases', 'results', 'graph', 'owners', 'qualification_report', 'cost_report', 'output', 'report']:
        parser.add_argument('--' + name.replace('_', '-'), type=Path, required=True)
    args = parser.parse_args()
    qualification = read_json(args.qualification_report)
    cases = read_json(args.cases)
    if not qualification.get('complete') or qualification.get('contexts') != 35393 or len(cases) != 35393:
        raise ValueError('Complete 35393-context native qualification required')
    cost = read_json(args.cost_report)
    if not cost.get('complete'):
        raise ValueError('Paired cost checks incomplete')
    rejected = {row['output'] for row in cost['results'] if row['reject_import']}
    plan = plan_qualified_imports(cases, read_json(args.results), read_json(args.graph),
                                  read_json(args.owners), rejected)
    text = ('"""Qualified imports for the pinned native GNU build; generated after full validation."""\n\n'
            'SHARED_PREFIX_IMPORTS = ' + json.dumps(plan['imports'], indent=4, sort_keys=True) + '\n')
    args.output.write_text(text)
    report = {key: value for key, value in plan.items() if key != 'imports'}
    report['input_sha256'] = {}
    for name in ['cases', 'results', 'graph', 'owners', 'qualification_report', 'cost_report']:
        path = getattr(args, name)
        with path.open('rb') as stream:
            report['input_sha256'][name] = hashlib.file_digest(stream, 'sha256').hexdigest()
    report['output_sha256'] = hashlib.sha256(text.encode()).hexdigest()
    args.report.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
