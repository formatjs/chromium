"""Generator output must not depend on executable paths or enclosing Git trees."""

import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from python.runfiles import runfiles


class GeneratorHermeticityTest(unittest.TestCase):
    def test_gperf_executable_location(self):
        with patch.dict(sys.modules, {'template_expander': types.ModuleType('template_expander')}):
            generate = runpy.run_path(str(GPERF_SCRIPT))['generate_gperf']
        source = '%language=C++\n%struct-type\nstruct Word { const char* name; int value; };\n%%\none, 1\ntwo, 2\n'
        with tempfile.TemporaryDirectory() as directory:
            outputs = []
            for name in ('first', 'different path'):
                path = Path(directory) / name / 'gperf'
                path.parent.mkdir()
                path.symlink_to(GPERF)
                outputs.append(generate(str(path), source, ['--key-positions=*', '-D']))
            self.assertEqual(outputs[0], outputs[1])
            self.assertIn('Command-line: gperf ', outputs[0])
            self.assertNotIn(directory, outputs[0])

    def test_staged_gperf_executable_location(self):
        with tempfile.TemporaryDirectory() as directory:
            outputs = []
            for name in ('first', 'different path'):
                root = Path(directory) / name
                root.mkdir()
                generator = root / 'generator.py'
                generator.write_text(
                    'import pathlib, sys, types\n'
                    'sys.modules["template_expander"] = types.ModuleType("template_expander")\n'
                    'from gperf import generate_gperf\n'
                    'source = "%language=C++\\n%%\\none\\ntwo\\n"\n'
                    'pathlib.Path("result.cc").write_text(generate_gperf("../../tools/gperf", source, []))\n')
                manifest = {
                    'inputs': [[str(generator), 'scripts/generator.py'],
                               [str(GPERF_SCRIPT), 'scripts/gperf.py'],
                               [str(GPERF), 'tools/gperf']],
                    'executable_inputs': ['tools/gperf'],
                    'executable_names': {'tools/gperf': 'gperf'},
                    'outputs': [['result.cc', 'result.cc']],
                    'build_dir': 'out/import', 'script': 'scripts/generator.py',
                    'args': [], 'response_file_contents': [],
                }
                (root / 'manifest.json').write_text(json.dumps(manifest))
                result = subprocess.run([str(Path(sys.executable).resolve()), str(ACTION_RUNNER), 'manifest.json'],
                                        cwd=root, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                outputs.append((root / 'result.cc').read_text())
            self.assertEqual(outputs[0], outputs[1])
            self.assertIn('Command-line: gperf ', outputs[0])
            self.assertNotIn(directory, outputs[0])

    def test_forced_spirv_version_never_invokes_git(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            git = root / 'git'
            git.write_text('#!/bin/sh\nprintf called >> "$GIT_PROBE_LOG"\nprintf "%s\\n" "$FAKE_GIT_DESCRIPTION"\n')
            git.chmod(0o755)
            outputs = []
            for name in ('parent-one', 'parent-two'):
                path = root / name
                path.mkdir()
                shutil.copyfile(CHANGES, path / 'CHANGES')
                marker = path / 'git-called'
                output = path / 'version.inc'
                environment = dict(os.environ, PATH=str(root), SOURCE_DATE_EPOCH='0',
                                   FORCED_BUILD_VERSION_DESCRIPTION='BCR-2026.1',
                                   GIT_PROBE_LOG=str(marker), FAKE_GIT_DESCRIPTION=name)
                subprocess.run([sys.executable, str(VERSION_SCRIPT), str(path / 'CHANGES'), str(output)],
                               cwd=path, env=environment, check=True, capture_output=True, text=True)
                self.assertFalse(marker.exists(), 'Version generation invoked ambient Git')
                outputs.append(output.read_bytes())
            self.assertEqual(outputs[0], outputs[1])
            self.assertIn(b'BCR-2026.1', outputs[0])
            self.assertEqual(VERSION_OUTPUT.read_bytes(), outputs[0])


if __name__ == '__main__':
    resolver = runfiles.Create()
    GPERF, ACTION_RUNNER, GPERF_SCRIPT, VERSION_SCRIPT, CHANGES, VERSION_OUTPUT = [
        Path(resolver.Rlocation(location)).resolve() for location in sys.argv[1:]
    ]
    del sys.argv[1:]
    unittest.main()
