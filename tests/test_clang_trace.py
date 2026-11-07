import json
from pathlib import Path
import tempfile
import unittest

from tools.ci.compile.clang_trace import compiler_trace_summary


class ClangTraceTest(unittest.TestCase):
    def test_nested_spans_do_not_double_compiler_total(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'trace.json'
            path.write_text(json.dumps({'traceEvents': [
                {'ph': 'X', 'name': name, 'dur': duration} for name, duration in [
                    ('ExecuteCompiler', 1000000), ('Frontend', 600000), ('Backend', 400000),
                    ('Total ExecuteCompiler', 1000000), ('Total Frontend', 600000),
                    ('Total Backend', 400000), ('Total Source', 1800000),
                ]]}))
            report = compiler_trace_summary(path)
            self.assertEqual(report['compiler_seconds'], 1)
            self.assertEqual(report['frontend_seconds'], .6)
            self.assertEqual(report['backend_seconds'], .4)
            self.assertTrue(report['nested_totals_are_not_additive'])
            path.write_text(json.dumps({'traceEvents': [{'ph': 'X', 'name': 'Frontend', 'dur': 1000}]}))
            with self.assertRaisesRegex(ValueError, 'Complete Clang compiler total'):
                compiler_trace_summary(path)


if __name__ == '__main__':
    unittest.main()
