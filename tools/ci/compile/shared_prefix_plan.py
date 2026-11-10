"""Keep added PCH imports acyclic across captured native compile owners."""


class PrefixCycleGuard:
    """Track imports against existing producer dependencies before editing rules."""

    def __init__(self, owners, producer_owners, producer_dependencies=None):
        owners = list(owners)
        if len(set(owners)) != len(owners):
            raise ValueError('Duplicate compile owner')
        self._incoming = dict.fromkeys(owners, 0)
        self._indices = {name: index for index, name in enumerate(producer_owners)}
        self._reachable = [1 << index for index in range(len(self._indices))]
        for producer, dependencies in (producer_dependencies or {}).items():
            origin = self._indices[producer]
            for dependency in dependencies:
                if dependency == producer:
                    raise ValueError('Producer depends on itself')
                self._reachable[origin] |= 1 << self._indices[dependency]
        for via in range(len(self._indices)):
            for origin in range(len(self._indices)):
                if self._reachable[origin] & (1 << via):
                    self._reachable[origin] |= self._reachable[via]
        for origin in range(len(self._indices)):
            for other in range(origin):
                if (self._reachable[origin] & (1 << other)
                        and self._reachable[other] & (1 << origin)):
                    raise ValueError('Existing producer dependencies contain a cycle')
        for producer, dependencies in producer_owners.items():
            dependency_owners = set(dependencies)
            unknown = dependency_owners.difference(self._incoming)
            if unknown:
                raise ValueError('Uncaptured compile owners: ' + ', '.join(sorted(unknown)))
            bit = 1 << self._indices[producer]
            for owner in dependency_owners:
                self._incoming[owner] |= bit
        # A producer also inherits every downstream producer's existing owners.
        for owner, incoming in self._incoming.items():
            self._incoming[owner] = sum(
                1 << origin for origin, reachable in enumerate(self._reachable)
                if reachable & incoming
            )

    @classmethod
    def from_capture(cls, capture):
        owners = capture['owner_order']
        producers = capture['prefix_order']
        if len(set(producers)) != len(producers):
            raise ValueError('Duplicate producer')
        owner_masks = {name: int(value, 16) for name, value in capture['producer_owner_masks'].items()}
        prefix_masks = {name: int(value, 16) for name, value in capture['producer_prefix_masks'].items()}
        if set(owner_masks) != set(producers) or set(prefix_masks) != set(producers):
            raise ValueError('Producer inventory differs from dependency masks')
        if any(mask < 0 or mask >> len(owners) for mask in owner_masks.values()):
            raise ValueError('Owner mask exceeds captured inventory')
        for index, name in enumerate(producers):
            mask = prefix_masks[name]
            if mask < 0 or mask >> len(producers) or not mask & (1 << index):
                raise ValueError('Invalid producer dependency mask')
        return cls(
            owners,
            {name: [owner for index, owner in enumerate(owners) if owner_masks[name] & (1 << index)]
             for name in producers},
            {name: [dependency for index, dependency in enumerate(producers)
                    if dependency != name and prefix_masks[name] & (1 << index)]
             for name in producers},
        )

    def allows(self, owner, producer):
        return not self._reachable[self._indices[producer]] & self._incoming[owner]

    def add_import(self, owner, producer):
        """Add one import, or leave the graph unchanged if it would create a cycle."""
        if not self.allows(owner, producer):
            return False
        incoming = self._incoming[owner]
        descendants = self._reachable[self._indices[producer]]
        for origin, reachable in enumerate(self._reachable):
            if reachable & incoming:
                self._reachable[origin] |= descendants
        return True


def plan_qualified_imports(cases, results, capture, owner_catalog, rejected_outputs=()):
    """Select byte-proven imports while preserving archive cohorts and the DAG."""
    from collections import Counter, defaultdict
    from pathlib import PurePosixPath

    def stem(path):
        return PurePosixPath(path.rsplit(':', 1)[-1]).stem

    def producer(case, route):
        scope, mode = route.rsplit('_', 1)
        if mode not in ('normal', 'eager'):
            raise ValueError('Unknown shared prefix mode: ' + route)
        if scope == 'targeted':
            name = 'shared_component_' + case['group']
        elif scope == 'global':
            name = 'shared_global_' + case['group']
        elif scope == 'sdk' and case['sdk_family'] is not None:
            name = 'shared_sdk_' + str(case['sdk_family'])
        else:
            raise ValueError('Unknown shared prefix route: ' + route)
        return name + '_' + mode + '_pch'

    by_output = {row['output']: row for row in results}
    expected = {row['output'] for row in cases}
    if len(by_output) != len(results) or len(expected) != len(cases) or set(by_output) != expected:
        raise ValueError('Qualification must cover every source exactly once')
    catalog = {row['attributes']['name']: row for row in owner_catalog}
    if len(catalog) != len(owner_catalog):
        raise ValueError('Duplicate source owner in catalog')
    stem_counts = {name: Counter(stem(source) for source in row['attributes']['srcs']
                                 if source.endswith(('.cc', '.cpp', '.cxx')))
                   for name, row in catalog.items() if row['kind'] != 'chromium_pch_compile'}
    rejected_outputs = set(rejected_outputs)
    if not rejected_outputs <= expected:
        raise ValueError('Cost rejection outside qualified population')
    proposals = {}
    skipped = Counter()
    units = defaultdict(list)
    for case in cases:
        record = by_output[case['output']]
        if (not record['complete'] or record['reference_sha256'] != case['reference_sha256']
                or record['command_environment_signature'] != case['command_environment_signature']
                or record['full_sdk_inputs'] != 1729 or record['source'] != case['source']
                or record['target'] != case['target']):
            raise ValueError('Qualification provenance differs: ' + case['output'])
        name = case['target'].rsplit(':', 1)[-1]
        owner = catalog[name]
        if owner['kind'] != 'chromium_pch_compile':
            counts = stem_counts[name]
            if not counts[stem(case['source'])]:
                raise ValueError('Source stem missing from owner catalog')
            unit = (case['target'], stem(case['source'])) if counts[stem(case['source'])] > 1 else (case['output'],)
        else:
            unit = (case['output'],)
        units[unit].append(case)
        if record['route'] == 'original':
            skipped['original'] += 1
            continue
        last = record['attempts'][-1]
        if (last['returncode'] != 0 or last['sha256'] != case['reference_sha256']
                or last['route'] != record['route']):
            raise ValueError('Accepted import differs from cold object: ' + case['output'])
        if case['output'] in rejected_outputs:
            skipped['cost'] += 1
            continue
        if owner['kind'] == 'cc_library' and owner['attributes'].get('linkstatic') is not True:
            skipped['dynamic_library'] += 1
            continue
        if owner['kind'] not in ('cc_library', 'cc_binary', 'chromium_pch_compile'):
            raise ValueError('Unsupported compile owner: ' + name)
        candidate = producer(case, record['route'])
        if candidate not in capture['prefix_order']:
            raise ValueError('Uncaptured producer: ' + candidate)
        proposals[case['output']] = candidate
    guard = PrefixCycleGuard.from_capture(capture)
    imports = defaultdict(dict)
    blocked = []
    for members in sorted(units.values(), key=lambda rows: (rows[0]['group'] == 'plain', rows[0]['target'], rows[0]['source'])):
        candidates = {proposals[row['output']] for row in members if row['output'] in proposals}
        if not candidates:
            continue
        case = members[0]
        name = case['target'].rsplit(':', 1)[-1]
        owner = catalog[name]
        required = len(members)
        # A .cxx fallback absent from qualification must keep its colliding peers original.
        if owner['kind'] != 'chromium_pch_compile':
            collisions = stem_counts[name][stem(case['source'])]
            required = max(required, collisions)
        if len(candidates) != 1 or sum(row['output'] in proposals for row in members) != required:
            skipped['duplicate_cohort'] += sum(row['output'] in proposals for row in members)
            continue
        candidate = next(iter(candidates))
        if not guard.add_import(case['target'], candidate):
            blocked.extend(row['output'] for row in members)
            skipped['cycle'] += len(members)
            continue
        for row in members:
            imports[name][row['source']] = ':' + candidate
    imports = {name: dict(sorted(sources.items())) for name, sources in sorted(imports.items())}
    return {'imports': imports, 'qualified_contexts': len(cases),
            'selected_contexts': sum(map(len, imports.values())), 'selected_owners': len(imports),
            'skipped': dict(skipped), 'cycle_blocked_outputs': blocked}
