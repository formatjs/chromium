"""Run a command with an empty, bounded private RAM sandbox on Linux."""

import argparse
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time


def run_command(command):
    child = subprocess.Popen(command, start_new_session=True)

    def forward(signum, _frame):
        try:
            os.killpg(child.pid, signum)
        except ProcessLookupError:
            pass

    signal.signal(signal.SIGINT, forward)
    signal.signal(signal.SIGTERM, forward)
    # PID 1 must also reap detached Bazel servers after shutdown.
    while True:
        pid, status = os.waitpid(-1, 0)
        if pid == child.pid:
            child.returncode = os.waitstatus_to_exitcode(status)
            return child.returncode if child.returncode >= 0 else 128 - child.returncode


def main():
    started = time.monotonic()
    if len(sys.argv) > 1 and sys.argv[1] == '_mount':
        size, mount, original_namespace, uid, *command = sys.argv[2:]
        if os.readlink('/proc/self/ns/mnt') == original_namespace or os.geteuid() != int(uid):
            raise ValueError('Private mount namespace and unchanged UID required')
        directory = Path(mount)
        if directory.is_symlink() or not directory.is_dir() or any(directory.iterdir()):
            raise ValueError('RAM mount point must be an empty owned directory')
        subprocess.run(['mount', '-t', 'tmpfs', '-o',
                        'size=' + size + 'g,nodev,nosuid,mode=0700', 'tmpfs', mount], check=True)
        command = [argument.replace('{sandbox}', mount) for argument in command]
        # Drop setup capabilities before starting the build, retaining its UID.
        return run_command(['setpriv', '--ambient-caps=-all', '--inh-caps=-all', *command])

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--size-gib', type=int, default=16)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    if args.size_gib < 1 or not command or not any('{sandbox}' in value for value in command):
        parser.error('Provide positive --size-gib and a command using {sandbox}')
    with tempfile.TemporaryDirectory(prefix='chromium-ram-sandbox-', dir='/tmp') as directory:
        environment = os.environ.copy()
        environment['CHROMIUM_LOCAL_COLD_STARTED'] = str(started)
        result = subprocess.run([
            'unshare', '--user', '--map-current-user', '--mount', '--propagation', 'private',
            '--keep-caps', '--pid', '--fork', '--kill-child', '--mount-proc',
            sys.executable, str(Path(__file__).resolve()), '_mount', str(args.size_gib), directory,
            os.readlink('/proc/self/ns/mnt'), str(os.geteuid()), *command,
        ], env=environment)
    return result.returncode


if __name__ == '__main__':
    sys.exit(main())
