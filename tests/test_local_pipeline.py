from pathlib import Path
import unittest
from unittest import mock

from tools.ci.compile import local_pipeline as local_throughput


class LocalThroughputTest(unittest.TestCase):
    def test_output_deletion_inventory_is_confined_and_unique(self):
        root = Path('/private/benchmark/execroot/_main')
        prefix = 'bazel-out/k8-fastbuild/bin/tools/ci/compile/local_throughput/_objs/probe/'
        valid = [prefix + 'first.o', prefix + 'second.pic.o']
        with mock.patch.object(local_throughput, 'SOURCES', ('first.cc', 'second.cc')):
            self.assertEqual(local_throughput.object_paths([valid], root),
                             [root / path for path in valid])
            for rows in [[valid[:1]], [[valid[0], valid[0]]],
                         [[valid[0], prefix + '../outside.o']],
                         [[valid[0], '/outside.o']],
                         [[valid[0], prefix + 'input.h']]]:
                with self.subTest(rows=rows), self.assertRaises(ValueError):
                    local_throughput.object_paths(rows, root)


if __name__ == '__main__':
    unittest.main()
