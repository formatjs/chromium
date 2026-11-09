"""Read Linux resource counters; missing counters stay unknown."""

import os
import math
from pathlib import Path


def resource_snapshot(pid=None, proc=Path('/proc'), cgroups=Path('/sys/fs/cgroup')):
    def text(path):
        try:
            return path.read_text()
        except OSError:
            return ''

    def counters(path, allowed):
        result = {}
        for line in text(path).splitlines():
            fields = line.split()
            if len(fields) == 2 and fields[0] in allowed and fields[1].isdigit():
                result[fields[0]] = int(fields[1])
        return result

    def pressure(path):
        result = {}
        for line in text(path).splitlines():
            fields = line.split()
            if not fields or fields[0] not in ('some', 'full'):
                continue
            values = {}
            for field in fields[1:]:
                key, separator, value = field.partition('=')
                if separator and key == 'total' and value.isdigit():
                    values['total_usec'] = int(value)
                elif separator and key in ('avg10', 'avg60', 'avg300'):
                    try:
                        number = float(value)
                        if math.isfinite(number) and 0 <= number <= 100:
                            values[key + '_percent'] = number
                    except ValueError:
                        pass
            result[fields[0]] = values
        return result

    result = {'scope': 'Cumulative counters; compare sample deltas. Kernel and ancestor views may include other workloads.'}
    first = text(proc / 'stat').splitlines()
    if first:
        fields = first[0].split()
        if fields and fields[0] == 'cpu' and all(value.isdigit() for value in fields[1:]):
            names = ['user', 'nice', 'system', 'idle', 'iowait', 'irq', 'softirq', 'steal', 'guest', 'guest_nice']
            result['kernel_cpu_ticks'] = dict(zip(names, map(int, fields[1:])))
            result['clock_ticks_per_second'] = os.sysconf('SC_CLK_TCK')
    result['kernel_pressure'] = {name: pressure(proc / 'pressure' / name) for name in ['cpu', 'memory', 'io']}
    groups = []
    for line in text(proc / 'self/cgroup').splitlines():
        if not line.startswith('0::'):
            continue
        relative = Path(line[3:].lstrip('/'))
        if '..' in relative.parts:
            continue
        path = cgroups / relative
        while path.is_relative_to(cgroups):
            row = {'depth_from_leaf': len(groups)}
            row['cpu_stat'] = counters(path / 'cpu.stat', {
                'usage_usec', 'user_usec', 'system_usec', 'nr_periods', 'nr_throttled',
                'throttled_usec', 'nr_bursts', 'burst_usec'})
            row['memory_events'] = counters(path / 'memory.events', {
                'low', 'high', 'max', 'oom', 'oom_kill', 'oom_group_kill'})
            row['memory_stat'] = counters(path / 'memory.stat', {
                'anon', 'file', 'shmem', 'pgfault', 'pgmajfault', 'workingset_refault_file'})
            for name in ['memory.current', 'memory.peak', 'memory.swap.current']:
                value = text(path / name).strip()
                if value.isdigit():
                    row[name.replace('.', '_') + '_bytes'] = int(value)
            row['pressure'] = {name: pressure(path / (name + '.pressure')) for name in ['cpu', 'memory', 'io']}
            groups.append(row)
            if path == cgroups:
                break
            path = path.parent
        break
    result['cgroups'] = groups
    if pid is not None:
        result['bazel_process'] = {}
        for line in text(proc / str(pid) / 'status').splitlines():
            key, _, value = line.partition(':')
            if key in ('VmRSS', 'VmHWM', 'VmSwap') and value.strip().endswith(' kB'):
                value = value.split()[0]
                if value.isdigit():
                    result['bazel_process'][key + '_bytes'] = int(value) * 1024
        # Split after command name; it may contain spaces and parentheses.
        command, separator, values = text(proc / str(pid) / 'stat').rpartition(')')
        fields = values.split()
        if (separator and command.startswith(str(pid) + ' (') and len(fields) >= 15
                and all(value.isascii() and value.isdigit() for value in fields[11:15])):
            rate = os.sysconf('SC_CLK_TCK')
            names = ('cpu_user_seconds', 'cpu_system_seconds',
                     'reaped_children_user_seconds', 'reaped_children_system_seconds')
            result['bazel_process'].update({name: int(value) / rate
                                           for name, value in zip(names, fields[11:15])})
    return result
