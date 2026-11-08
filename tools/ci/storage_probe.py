"""Record runner filesystem capacity without changing build state."""

import argparse
import json
from pathlib import Path
import os

from tools.ci.chromium import ROOT
from tools.ci.local_cold import machine_limits


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    args.directory.mkdir(parents=True, exist_ok=False)
    paths = {}
    for name, path in [("workspace", ROOT), ("temporary", Path("/tmp")),
                       ("home", Path.home()), ("artifacts", args.directory)]:
        path = path.resolve()
        state = os.statvfs(path)
        paths[name] = {"path": str(path), "device": os.stat(path).st_dev,
                       "capacity_bytes": state.f_blocks * state.f_frsize,
                       "available_bytes": state.f_bavail * state.f_frsize,
                       "capacity_inodes": state.f_files, "available_inodes": state.f_favail}
    report = {"scope": "Read-only filesystem diagnostic; no build or cold timing claim",
              "machine": machine_limits(), "filesystems": paths}
    (args.directory / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
