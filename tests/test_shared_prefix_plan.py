import random
import unittest

from tools.ci.compile.shared_prefix_plan import PrefixCycleGuard


def acyclic(edges):
    indegree = dict.fromkeys(edges, 0)
    for dependencies in edges.values():
        for dependency in dependencies:
            indegree[dependency] += 1
    ready = [node for node, count in indegree.items() if not count]
    visited = 0
    while ready:
        node = ready.pop()
        visited += 1
        for dependency in edges[node]:
            indegree[dependency] -= 1
            if not indegree[dependency]:
                ready.append(dependency)
    return visited == len(edges)


class PrefixCycleGuardTest(unittest.TestCase):
    def test_rejects_direct_and_combined_cycles_without_poisoning_fallback(self):
        guard = PrefixCycleGuard(['a', 'b'], {'p': ['a'], 'q': ['b'], 'sdk': []})
        self.assertFalse(guard.add_import('a', 'p'))
        self.assertTrue(guard.add_import('a', 'q'))
        self.assertFalse(guard.add_import('b', 'p'))
        self.assertTrue(guard.add_import('b', 'sdk'))
        self.assertTrue(guard.add_import('a', 'q'))

    def test_matches_whole_graph_cycle_checks_across_import_sequences(self):
        randomizer = random.Random(1729)
        owners = ['owner' + str(index) for index in range(12)]
        producers = ['prefix' + str(index) for index in range(8)]
        for _ in range(20):
            producer_owners = {
                producer: [owner for owner in owners if randomizer.random() < 0.15]
                for producer in producers
            }
            dependencies = {
                producer: [earlier for earlier in producers[:index] if randomizer.random() < 0.1]
                for index, producer in enumerate(producers)
            }
            guard = PrefixCycleGuard(owners, producer_owners, dependencies)
            edges = {owner: set() for owner in owners}
            edges.update({producer: set(producer_owners[producer] + dependencies[producer])
                          for producer in producers})
            for _ in range(100):
                owner = randomizer.choice(owners)
                producer = randomizer.choice(producers)
                trial = {node: set(values) for node, values in edges.items()}
                trial[owner].add(producer)
                expected = acyclic(trial)
                self.assertEqual(guard.allows(owner, producer), expected)
                self.assertEqual(guard.add_import(owner, producer), expected)
                if expected:
                    edges = trial

    def test_capture_validation_and_uncaptured_owners(self):
        capture = {'owner_order': ['a'], 'prefix_order': ['p', 'sdk'],
                   'producer_owner_masks': {'p': '0x1', 'sdk': '0x0'},
                   'producer_prefix_masks': {'p': '0x1', 'sdk': '0x2'}}
        guard = PrefixCycleGuard.from_capture(capture)
        self.assertFalse(guard.add_import('a', 'p'))
        self.assertTrue(guard.add_import('a', 'sdk'))
        with self.assertRaises(KeyError):
            guard.add_import('unknown', 'sdk')
        capture['producer_owner_masks']['p'] = '0x2'
        with self.assertRaisesRegex(ValueError, 'Owner mask'):
            PrefixCycleGuard.from_capture(capture)
        with self.assertRaisesRegex(ValueError, 'cycle'):
            PrefixCycleGuard(['a'], {'p': [], 'q': []}, {'p': ['q'], 'q': ['p']})


if __name__ == '__main__':
    unittest.main()
