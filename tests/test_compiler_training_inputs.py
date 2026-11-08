import ast
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from tools.ci.compiler_training_inputs import compile_flags, install_inputs


class CompilerTrainingInputsTest(unittest.TestCase):
    def test_preprocessed_flags_preserve_codegen_without_external_inputs(self):
        arguments = ['-target', 'x86_64-linux-gnu', '-std=c++20', '-O2', '-fno-exceptions',
                     '-Iexternal/chromium', '-DCHROMIUM=1', '--sysroot=/dev/null',
                     '-Xclang', '-internal-isystem', '-Xclang', 'external/llvm/include',
                     '-mllvm', '-instcombine-lower-dbg-declare=0',
                     '-frandom-seed=bazel-out/original.o', '-c', 'external/chromium/source.cc',
                     '-MD', '-MF', 'bazel-out/source.d', '-o', 'bazel-out/source.ii', '-E']
        self.assertEqual(compile_flags(arguments, 'external/chromium/source.cc'), [
            '-x', 'c++-cpp-output', '-target', 'x86_64-linux-gnu', '-std=c++20', '-O2',
            '-fno-exceptions', '-mllvm', '-instcombine-lower-dbg-declare=0',
            '-frandom-seed=bazel-out/original.o', '-Xclang', '-main-file-name', '-Xclang', 'source.cc',
        ])
        for invalid in [arguments + ['-I'], arguments + ['external/undeclared.o'],
                        arguments + ['external/chromium/source.cc']]:
            with self.subTest(arguments=invalid), self.assertRaises(ValueError):
                compile_flags(invalid, 'external/chromium/source.cc')

    def test_import_records_exact_bytes_and_emits_declared_starlark_inputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            inputs, workspace = root / 'inputs', root / 'workspace'
            inputs.mkdir()
            (workspace / 'toolchain/bootstrap/stage3').mkdir(parents=True)
            for name in ['v8', 'content']:
                stem = 'llvm_training_' + name
                (inputs / (stem + '.ii')).write_text('int ' + name + ' = 1;\n')
                (inputs / (stem + '.json')).write_text(json.dumps({
                    'source': 'external/chromium/' + name + '.cc',
                    'preprocessed': 'bazel-out/' + stem + '.ii',
                    'compiler': 'external/llvm/bin/clang++',
                    'arguments': ['-target', 'x86_64-linux-gnu', '-c',
                                  'external/chromium/' + name + '.cc', '-E'],
                }))
            result = install_inputs(inputs, workspace)
            destination = workspace / 'toolchain/bootstrap/stage3/chromium_training'
            workloads = ast.literal_eval((destination / 'inputs.bzl').read_text().split('=', 1)[1])
            self.assertEqual([entry['name'] for entry in workloads], ['v8', 'content'])
            for entry, metadata in zip(workloads, result):
                original = inputs / Path(entry['source']).name
                copied = destination / original.name
                self.assertEqual(copied.read_bytes(), original.read_bytes())
                self.assertEqual(metadata['preprocessed_sha256'], hashlib.sha256(copied.read_bytes()).hexdigest())
                self.assertEqual(entry['flags'][:4], ['-x', 'c++-cpp-output', '-target', 'x86_64-linux-gnu'])
            self.assertEqual(json.loads((destination / 'provenance.json').read_text()), result)


if __name__ == '__main__':
    unittest.main()
