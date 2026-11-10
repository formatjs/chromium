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


class QualifiedImportPlanTest(unittest.TestCase):
    def fixture(self, names=('a', 'b'), filenames=('left/same.cc', 'right/same.cpp')):
        from copy import deepcopy
        producer = 'shared_sdk_0_eager_pch'
        owners = ['@@+chromium_dependencies+chromium//native:' + name for name in names]
        cases = [dict(output='out' + str(index), source=filename, target=owner,
                      group='plain', sdk_family=0, reference_sha256='a' * 64,
                      command_environment_signature='b' * 64)
                 for index, (owner, filename) in enumerate(zip(owners, filenames))]
        results = [dict(deepcopy(case), complete=True, full_sdk_inputs=1729, route='sdk_eager',
                        attempts=[dict(route='sdk_eager', returncode=0, sha256='a' * 64)])
                   for case in cases]
        catalog = [dict(kind='cc_library', attributes=dict(name=name, linkstatic=True,
                                                         srcs=[filename]))
                   for name, filename in zip(names, filenames)]
        capture = dict(owner_order=list(dict.fromkeys(owners)), prefix_order=[producer],
                       producer_owner_masks={producer: '0x0'}, producer_prefix_masks={producer: '0x1'})
        return cases, results, capture, catalog

    def test_requires_complete_byte_and_environment_proof(self):
        from tools.ci.compile.shared_prefix_plan import plan_qualified_imports
        cases, results, capture, catalog = self.fixture()
        with self.assertRaisesRegex(ValueError, 'every source'):
            plan_qualified_imports(cases, results[:1], capture, catalog)
        results[0]['attempts'][0]['sha256'] = 'c' * 64
        with self.assertRaisesRegex(ValueError, 'cold object'):
            plan_qualified_imports(cases, results, capture, catalog)
        results[0]['command_environment_signature'] = 'c' * 64
        with self.assertRaisesRegex(ValueError, 'provenance'):
            plan_qualified_imports(cases, results, capture, catalog)

    def test_cost_and_dynamic_capability_keep_original_rules(self):
        from tools.ci.compile.shared_prefix_plan import plan_qualified_imports
        cases, results, capture, catalog = self.fixture()
        catalog[1]['attributes'].pop('linkstatic')
        plan = plan_qualified_imports(cases, results, capture, catalog, {cases[0]['output']})
        self.assertEqual(plan['imports'], {})
        self.assertEqual(plan['skipped'], {'cost': 1, 'dynamic_library': 1})

    def test_duplicate_stems_stay_atomic_including_unqualified_cxx(self):
        from tools.ci.compile.shared_prefix_plan import plan_qualified_imports
        cases, results, capture, catalog = self.fixture(names=('a', 'a'))
        catalog = [catalog[0]]
        catalog[0]['attributes']['srcs'] = ['left/same.cc', 'right/same.cpp']
        plan = plan_qualified_imports(cases, results, capture, catalog)
        self.assertEqual(plan['selected_contexts'], 2)
        plan = plan_qualified_imports(cases, results, capture, catalog, {cases[0]['output']})
        self.assertEqual(plan['selected_contexts'], 0)
        self.assertEqual(plan['skipped']['duplicate_cohort'], 1)
        catalog[0]['attributes']['srcs'].append('third/same.cxx')
        self.assertEqual(plan_qualified_imports(cases, results, capture, catalog)['selected_contexts'], 0)

    def test_native_cycle_rejection_keeps_other_imports(self):
        from tools.ci.compile.shared_prefix_plan import plan_qualified_imports
        cases, results, capture, catalog = self.fixture()
        capture['producer_owner_masks']['shared_sdk_0_eager_pch'] = '0x1'
        plan = plan_qualified_imports(cases, results, capture, catalog)
        self.assertEqual(plan['cycle_blocked_outputs'], ['out0'])
        self.assertEqual(plan['selected_contexts'], 1)


if __name__ == '__main__':
    unittest.main()
