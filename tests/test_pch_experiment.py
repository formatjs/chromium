from pathlib import Path
import hashlib
import tempfile
import unittest
from unittest import mock

from tools.ci.compile import pch_experiment
from tools.ci.compile.pch_reproducibility import verify_producer_options


class PchExperimentTest(unittest.TestCase):
    def test_producer_requires_timestamp_free_content_validation(self):
        flags = ['--relocatable-pch', '-Xclang', '-fno-pch-timestamp',
                 '-fpch-validate-input-files-content']
        verify_producer_options(flags)
        for missing in ['-Xclang', '-fno-pch-timestamp', '-fpch-validate-input-files-content']:
            with self.subTest(missing=missing), self.assertRaises(ValueError):
                verify_producer_options([flag for flag in flags if flag != missing])
        for bypass in ['-fno-validate-pch', '-disable-pch-validation']:
            with self.subTest(bypass=bypass), self.assertRaises(ValueError):
                verify_producer_options(flags + [bypass])

    def test_compiler_verification_works_before_execroot_symlinks_exist(self):
        with tempfile.TemporaryDirectory() as temporary:
            output_base = Path(temporary)
            relative = 'external/pinned-llvm/bin/clang++'
            binary = output_base / relative
            binary.parent.mkdir(parents=True)
            binary.write_bytes(b'pinned compiler')
            commands = {'source.cc': ([relative], {})}
            expected = hashlib.sha256(binary.read_bytes()).hexdigest()
            pch_experiment.verify_command_compilers(commands, output_base, expected)
            binary.write_bytes(b'changed compiler')
            with self.assertRaises(ValueError):
                pch_experiment.verify_command_compilers(commands, output_base, expected)
            for compiler in ['/usr/bin/clang++', 'external/../foreign/compiler']:
                with self.subTest(compiler=compiler), self.assertRaises(ValueError):
                    pch_experiment.verify_command_compilers({'source.cc': ([compiler], {})}, output_base, expected)

    def test_command_gate_preserves_macro_include_order_and_environment(self):
        def rows(owner, pch=False):
            return [([
                'clang++', '-DVALUE=1', '-Ifirst', '-Isecond', '-c', source,
                '-o', owner + '/' + source + '.o', '-MF', owner + '/' + source + '.d',
            ] + (['-fpch-validate-input-files-content', '-include-pch', 'probe.pch'] if pch else []), {'PATH': '/pinned/bin'})
                    for source in ['first.cc', 'second.cc']]
        with mock.patch.object(pch_experiment, 'SOURCES', ('first.cc', 'second.cc')):
            baseline = pch_experiment.normalized_commands(rows('baseline'))
            candidate = rows('candidate', pch=True)
            missing_validation = rows('candidate', pch=True)
            missing_validation[0][0].remove('-fpch-validate-input-files-content')
            with self.assertRaisesRegex(ValueError, 'content validation'):
                pch_experiment.normalized_commands(missing_validation, 'probe.pch')
            self.assertEqual(baseline, pch_experiment.normalized_commands(candidate, 'probe.pch'))
            for change in ['macro', 'include_order', 'environment']:
                changed = rows('candidate', pch=True)
                if change == 'macro':
                    changed[0][0][1] = '-DVALUE=2'
                elif change == 'include_order':
                    changed[0][0][2:4] = ['-Isecond', '-Ifirst']
                else:
                    changed[0][1]['PATH'] = '/different/bin'
                with self.subTest(change=change):
                    self.assertNotEqual(baseline, pch_experiment.normalized_commands(changed, 'probe.pch'))
            with self.assertRaises(ValueError):
                pch_experiment.normalized_commands(candidate, 'different.pch')
            with self.assertRaises(ValueError):
                pch_experiment.normalized_commands(candidate)
            with self.assertRaises(ValueError):
                pch_experiment.normalized_commands([candidate[0], candidate[0]], 'probe.pch')

    def test_project_gate_only_changes_existing_header_consumers(self):
        baseline = [(['clang++', '-DVALUE=1', '-c', source, '-o', source + '.o',
                     '-isysroot', '.'], {}) for source in ['first.cc', 'second.cc']]
        candidate = [([*baseline[0][0], '-ffile-prefix-map=./=', '-fpch-validate-input-files-content', '-include-pch', 'project.pch'], {}),
                     (baseline[1][0][:-2], {})]
        eligible = {'first.cc'}
        with mock.patch.object(pch_experiment, 'SOURCES', ('first.cc', 'second.cc')):
            expected = pch_experiment.normalized_commands(baseline, eligible_sources=eligible)
            self.assertEqual(expected, pch_experiment.normalized_commands(candidate, 'project.pch', eligible))
            for rows in [baseline,
                         [candidate[0], (baseline[1][0] + ['-include-pch', 'project.pch'], {})],
                         [(candidate[0][0][:-1] + ['wrong.pch'], {}), candidate[1]]]:
                with self.assertRaises(ValueError):
                    pch_experiment.normalized_commands(rows, 'project.pch', eligible)
            for index, flag in [(0, '-ffile-prefix-map=./='), (0, '-DVALUE=1')]:
                changed = [(list(a), dict(e)) for a, e in candidate]
                changed[index][0].remove(flag)
                if flag.startswith('-ffile-prefix-map'):
                    with self.assertRaises(ValueError):
                        pch_experiment.normalized_commands(changed, 'project.pch', eligible)
                else:
                    self.assertNotEqual(expected, pch_experiment.normalized_commands(changed, 'project.pch', eligible))

    def test_split_inventory_never_deletes_another_target(self):
        root = Path('/private/benchmark/execroot/_main')
        prefix = 'bazel-out/k8-fastbuild/bin/tools/ci/compile/pch/_objs/'
        valid = [prefix + 'probe_pch/first.pic.o', prefix + 'probe_plain/second.pic.o']
        with mock.patch.object(pch_experiment, 'SOURCES', ('first.cc', 'second.cc')):
            self.assertEqual(set(pch_experiment.owned_objects([valid], root, 'probe', split=True)),
                             {'first.pic.o', 'second.pic.o'})
            for other in ['probe/second.pic.o', 'other_plain/second.pic.o', 'probe_plain/../second.pic.o',
                          'probe_plain/first.pic.o']:
                with self.subTest(other=other), self.assertRaises(ValueError):
                    pch_experiment.owned_objects([[valid[0], prefix + other]], root, 'probe', split=True)

    def test_distinct_pch_inputs_and_original_fallback_are_verified(self):
        sources = ('document.cc', 'string.cc', 'plain.cc')
        baseline = [(['clang++', '-DVALUE=1', '-c', source, '-o', source + '.o'], {}) for source in sources]
        mapping = {'document.cc': 'document.pch', 'string.cc': 'string.pch'}
        eligible = set(mapping)
        candidate = [(args + (['-isysroot', '.', '-ffile-prefix-map=./=', '-fpch-validate-input-files-content', '-include-pch', mapping[source]]
                              if source in mapping else []), environment)
                     for source, (args, environment) in zip(sources, baseline)]
        with mock.patch.object(pch_experiment, 'SOURCES', sources):
            expected = pch_experiment.normalized_commands(baseline, eligible_sources=eligible)
            self.assertEqual(expected, pch_experiment.normalized_commands(candidate, mapping, eligible))
            for wrong in [{'document.cc': 'string.pch', 'string.cc': 'document.pch'},
                          {'document.cc': 'document.pch'}]:
                with self.subTest(mapping=wrong), self.assertRaises(ValueError):
                    pch_experiment.normalized_commands(candidate, wrong, eligible)
            root = Path('/private/execroot/_main')
            prefix = 'bazel-out/k8-fastbuild/bin/tools/ci/compile/pch/_objs/'
            paths = [prefix + 'probe_' + group + '/' + source + '.o'
                     for group, source in zip(('document', 'string', 'plain'), sources)]
            self.assertEqual(len(pch_experiment.owned_objects([paths], root, 'probe',
                                                            groups=('document', 'string', 'plain'))), 3)
            with self.assertRaises(ValueError):
                pch_experiment.owned_objects([paths], root, 'probe', groups=('document', 'plain'))

    def test_hybrid_baseline_inventory_stays_flat(self):
        root = Path('/private/execroot/_main')
        package = 'tools/ci/compile/pch'
        prefix = 'bazel-out/k8-fastbuild/bin/' + package + '/_objs/'
        flat = [prefix + 'probe_baseline/' + source + '.o' for source in ['a', 'b', 'c']]
        grouped = [prefix + 'probe_' + group + '/' + source + '.o'
                   for group, source in zip(('document', 'string', 'plain'), ('a', 'b', 'c'))]
        with mock.patch.object(pch_experiment, 'SOURCES', ('a.cc', 'b.cc', 'c.cc')):
            self.assertEqual(len(pch_experiment.probe_objects([flat], root, 'probe_baseline', package,
                                                            'baseline', hybrid=True)), 3)
            self.assertEqual(len(pch_experiment.probe_objects([grouped], root, 'probe', package,
                                                            'candidate', hybrid=True)), 3)
            with self.assertRaises(ValueError):
                pch_experiment.probe_objects([grouped], root, 'probe_baseline', package,
                                            'baseline', hybrid=True)

    def test_include_reduction_preserves_registry_toolchain_and_flag_order(self):
        root = 'external/+chromium_dependencies+chromium/'
        def rows(paths, define='-DVALUE=1', environment=None):
            return {'source.cc': (['clang++', define, *paths, '-c', 'source.cc'], environment or {'PATH': '/pinned'})}
        registry = '-Iexternal/abseil-cpp+/include'
        original = rows(['-I' + root + 'native/../base/private', registry,
                         '-iquote', 'bazel-out/k8-fastbuild/bin/' + root + 'native/private',
                         '-isystem', 'external/llvm-toolchain/include'])
        candidate = rows([registry, '-isystem', 'external/llvm-toolchain/include'])
        self.assertEqual(pch_experiment.verify_include_reduction(original, candidate), {
            'baseline_paths': 4, 'candidate_paths': 2, 'removed_paths': 2,
            'retained_order_verified': True, 'other_flags_and_environments_equal': True,
        })
        invalid = [
            rows([]),
            rows([registry, '-Iextra', '-isystem', 'external/llvm-toolchain/include']),
            rows(['-isystem', 'external/llvm-toolchain/include', registry]),
            rows([registry, '-isystem', 'external/llvm-toolchain/include'], define='-DVALUE=2'),
            rows([registry, '-isystem', 'external/llvm-toolchain/include'], environment={'PATH': '/foreign'}),
            {},
        ]
        for changed in invalid:
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                pch_experiment.verify_include_reduction(original, changed)

    def test_native_owner_inventory_keeps_count_and_path_guards(self):
        root = Path('/private/execroot/_main')
        package = 'external/+chromium_dependencies+chromium/native'
        prefix = 'bazel-out/k8-fastbuild/bin/' + package + '/_objs/module_pch_'
        paths = [prefix + 'idl/a.pic.o', prefix + 'plain/b.pic.o']
        inventory = pch_experiment.owned_objects([paths], root, 'module_pch',
                                                package=package, groups=('idl', 'plain'), expected_count=2)
        self.assertEqual(set(inventory), {'a.pic.o', 'b.pic.o'})
        for invalid in [paths[:1], paths + [prefix + 'idl/c.pic.o'],
                        [paths[0], paths[1].replace('/module_pch_', '/other_')]]:
            with self.subTest(paths=invalid), self.assertRaises(ValueError):
                pch_experiment.owned_objects([invalid], root, 'module_pch', package=package,
                                            groups=('idl', 'plain'), expected_count=2)
        commands = [(['clang++', '-c', name, '-o', name + '.o'], {}) for name in ['a.cc', 'b.cc']]
        self.assertEqual(len(pch_experiment.normalized_commands(commands, expected_count=2)), 2)
        for invalid in [commands[:1], commands + [(['clang++', '-c', 'c.cc'], {})]]:
            with self.subTest(commands=invalid), self.assertRaises(ValueError):
                pch_experiment.normalized_commands(invalid, expected_count=2)

    def test_deletion_inventory_rejects_foreign_duplicate_and_traversal_paths(self):
        root = Path('/private/benchmark/execroot/_main')
        owner = 'probe'
        prefix = 'bazel-out/k8-fastbuild/bin/tools/ci/compile/pch/_objs/probe/'
        valid = [prefix + 'first.pic.o', prefix + 'nested/second.pic.o']
        with mock.patch.object(pch_experiment, 'SOURCES', ('first.cc', 'second.cc')):
            self.assertEqual(pch_experiment.owned_objects([valid], root, owner), {
                'first.pic.o': root / valid[0], 'nested/second.pic.o': root / valid[1],
            })
            for invalid in [valid[:1], [valid[0], valid[0]],
                            [valid[0], prefix + '../foreign.o'],
                            [valid[0], '/foreign.o'],
                            [valid[0], prefix + 'input.h'],
                            [valid[0], valid[1].replace('_objs/probe/', '_objs/other/')]]:
                with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                    pch_experiment.owned_objects([invalid], root, owner)


if __name__ == '__main__':
    unittest.main()
