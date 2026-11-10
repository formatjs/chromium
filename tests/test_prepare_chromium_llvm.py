import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from tools.ci import prepare_chromium_llvm


class ChromiumPreparationArtifactsTest(unittest.TestCase):
    def test_replayable_inputs_survive_success_and_failed_compiler_guard(self):
        for failed in [False, True]:
            with self.subTest(failed=failed), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                outputs = root / 'bazel-out/training'
                outputs.mkdir(parents=True)
                originals = {}
                for name in ['v8', 'content']:
                    stem = 'llvm_training_' + name
                    values = {
                        '.ii': ('int ' + name + ' = 1;\n').encode(),
                        '.d': (stem + '.ii: ' + name + '.cc\n').encode(),
                        '.json': json.dumps({
                            'preprocessed': 'bazel-out/training/' + stem + '.ii',
                            'source': name + '.cc', 'compiler': 'pinned-clang',
                            'arguments': ['-c', name + '.cc', '-DVALUE=1',
                                          '-std=c++20', '-o', name + '.o'],
                        }).encode(),
                    }
                    for suffix, content in values.items():
                        path = outputs / (stem + suffix)
                        path.write_bytes(content)
                        originals[path] = content
                artifacts = root / 'artifacts'
                retained = root / 'artifacts-training-inputs/toolchain/bootstrap/stage3/chromium_training'

                def run(command, **kwargs):
                    if command[:3] == [sys.executable, '-m', 'tools.ci.prepare_llvm_bolt']:
                        self.assertTrue((retained / 'provenance.json').is_file())
                        self.assertTrue((retained / 'llvm_training_v8.ii').is_file())
                        if failed:
                            raise subprocess.CalledProcessError(23, command)
                    return subprocess.CompletedProcess(command, 0)

                query = '\n'.join(str(path.relative_to(root)) for path in originals)
                with patch.object(prepare_chromium_llvm, 'ROOT', root), \
                     patch.object(prepare_chromium_llvm.subprocess, 'run', side_effect=run), \
                     patch.object(prepare_chromium_llvm.subprocess, 'check_output', return_value=query), \
                     patch.dict(os.environ, {'BUILDBUDDY_CI_RUNNER_ABSPATH': '/runner'}), \
                     patch.object(sys, 'argv', ['prepare', '--directory', str(artifacts), '--bolt-feasibility']):
                    if failed:
                        with self.assertRaises(subprocess.CalledProcessError) as error:
                            prepare_chromium_llvm.main()
                        self.assertEqual(error.exception.returncode, 23)
                    else:
                        prepare_chromium_llvm.main()

                for path, content in originals.items():
                    self.assertEqual(path.read_bytes(), content)
                    self.assertEqual((retained / path.name).read_bytes(), content)
                provenance = json.loads((retained / 'provenance.json').read_text())
                self.assertEqual({row['name'] for row in provenance}, {'v8', 'content'})
                for row in provenance:
                    source = retained / ('llvm_training_' + row['name'] + '.ii')
                    self.assertEqual(row['preprocessed_sha256'], hashlib.sha256(source.read_bytes()).hexdigest())
                    self.assertIn('-std=c++20', row['flags'])
                    self.assertNotIn('-DVALUE=1', row['flags'])
                self.assertTrue((retained / 'inputs.bzl').is_file())
