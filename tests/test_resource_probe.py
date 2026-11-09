from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tools.ci.resource_probe import resource_snapshot


class ResourceProbeTest(unittest.TestCase):
    def test_process_cpu_keeps_units_and_handles_parentheses_in_command_name(self):
        with tempfile.TemporaryDirectory() as temporary:
            proc = Path(temporary)
            (proc / '7').mkdir()
            fields = ['S'] + ['0'] * 10 + ['250', '75', '400', '125']
            (proc / '7/stat').write_text('7 (private (worker) name) ' + ' '.join(fields) + '\n')
            with mock.patch('tools.ci.resource_probe.os.sysconf', return_value=100):
                result = resource_snapshot(7, proc, proc / 'unavailable')
            self.assertEqual(result['bazel_process'], {
                'cpu_user_seconds': 2.5, 'cpu_system_seconds': 0.75,
                'reaped_children_user_seconds': 4.0, 'reaped_children_system_seconds': 1.25,
            })
            self.assertNotIn('private', str(result))

    def test_exited_or_malformed_process_cpu_stays_unknown_without_losing_memory(self):
        with tempfile.TemporaryDirectory() as temporary:
            proc = Path(temporary)
            (proc / '7').mkdir()
            (proc / '7/status').write_text('VmRSS:\t12 kB\n')
            fields = ['S'] + ['0'] * 10 + ['250', '75', '400', '125']
            for value in ['', '7 (java) S', '8 (java) ' + ' '.join(fields),
                          '7 (java) ' + ' '.join(fields[:11] + ['bad'] + fields[12:]),
                          '7 (java) ' + ' '.join(fields[:11] + ['-1'] + fields[12:])]:
                (proc / '7/stat').write_text(value)
                with self.subTest(stat=value):
                    result = resource_snapshot(7, proc, proc / 'unavailable')
                    self.assertEqual(result['bazel_process'], {'VmRSS_bytes': 12288})
            (proc / '7/stat').unlink()
            self.assertEqual(resource_snapshot(7, proc, proc / 'unavailable')['bazel_process'],
                             {'VmRSS_bytes': 12288})

    def test_leaf_and_ancestor_counters_keep_units_and_missing_values(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            proc, groups = root / 'proc', root / 'cgroups'
            for path in [proc / 'self', proc / '7', proc / 'pressure', groups / 'job']:
                path.mkdir(parents=True)
            (proc / 'self/cgroup').write_text('0::/job\n')
            (proc / 'stat').write_text('cpu 10 20 30 40 50 60 70 80 9 0\ncpu0 1 2\n')
            (proc / '7/status').write_text('VmRSS:\t12 kB\nVmSwap:\t3 kB\nName:\tprivate-process-name\n')
            (groups / 'job/cpu.stat').write_text('usage_usec 100\nnr_throttled 2\nthrottled_usec 30\n')
            (groups / 'cpu.stat').write_text('usage_usec 200\n')
            (groups / 'job/memory.current').write_text('4096\n')
            (groups / 'job/memory.events').write_text('oom_kill 1\nhigh 3\n')
            (groups / 'job/io.pressure').write_text('some avg10=2.50 avg60=1.0 avg300=0.0 total=400\n')
            result = resource_snapshot(7, proc, groups)
            leaf, parent = result['cgroups']
            self.assertEqual(leaf['cpu_stat'], {'usage_usec': 100, 'nr_throttled': 2, 'throttled_usec': 30})
            self.assertEqual(parent['cpu_stat'], {'usage_usec': 200})
            self.assertEqual(leaf['memory_current_bytes'], 4096)
            self.assertNotIn('memory_peak_bytes', leaf)
            self.assertEqual(leaf['memory_events'], {'oom_kill': 1, 'high': 3})
            self.assertEqual(leaf['pressure']['io']['some']['total_usec'], 400)
            self.assertEqual(leaf['pressure']['io']['some']['avg10_percent'], 2.5)
            self.assertEqual(result['kernel_cpu_ticks']['steal'], 80)
            self.assertEqual(result['bazel_process'], {'VmRSS_bytes': 12288, 'VmSwap_bytes': 3072})
            self.assertEqual([row['depth_from_leaf'] for row in result['cgroups']], [0, 1])

    def test_unavailable_or_malformed_counters_do_not_break_build_or_become_zero(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            proc = root / 'proc'
            (proc / 'self').mkdir(parents=True)
            (proc / 'pressure').mkdir()
            (proc / 'stat').write_text('\n')
            (proc / 'self/cgroup').write_text('0::/../../outside\n')
            (proc / 'pressure/memory').write_text('some avg10=nan avg60=bad total=no\n')
            result = resource_snapshot(100, proc, root / 'unavailable')
            self.assertEqual(result['cgroups'], [])
            self.assertNotIn('kernel_cpu_ticks', result)
            self.assertEqual(result['bazel_process'], {})
            self.assertEqual(result['kernel_pressure']['memory'], {'some': {}})


if __name__ == '__main__':
    unittest.main()
