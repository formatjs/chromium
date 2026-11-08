from pathlib import Path
import hashlib
import tempfile
import unittest
from unittest import mock

from tools.ci.compile import pch_experiment


class PchExperimentTest(unittest.TestCase):
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
            ] + (['-include-pch', 'probe.pch'] if pch else []), {'PATH': '/pinned/bin'})
                    for source in ['first.cc', 'second.cc']]
        with mock.patch.object(pch_experiment, 'SOURCES', ('first.cc', 'second.cc')):
            baseline = pch_experiment.normalized_commands(rows('baseline'))
            candidate = rows('candidate', pch=True)
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
