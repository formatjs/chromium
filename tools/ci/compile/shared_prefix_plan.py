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
