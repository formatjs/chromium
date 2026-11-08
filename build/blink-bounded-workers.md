# Bounded Blink workers experiment

The partial strict-cold trace records one 569.83s bindings action. Production
uses upstream serial mode. Test whether four explicitly budgeted workers shorten
this dependency without changing generated files.

`--define=CHROMIUM_BINDINGS_WORKERS=2` or `4` selects a bounded upstream pool.
Bazel reserves the same CPU count and 1GiB or 2GiB of memory. Default `1` retains
serial arguments. Invalid counts fail analysis; parallel mode rejects conflicting
script arguments. No host CPU-count override or global multiprocessing patch.
The source patch adds a worker-count argument; generator algorithms stay intact.

Run `tools.ci.binding_workers` through `tools.ci.compile.private_ram` with a
private sandbox and explicit archive download cache. Two warmups then ABBA
serial/four-worker passes compare all 5,574 core bindings outputs. A completed
real generator profile span is mandatory for every pass. Supporting state stays
warm; neither this probe nor its total duration proves cold-build performance.

Pinned-source patch application, Python compilation and real Bazel action
analysis pass. Analysis confirms `--worker_processes=4` and 5,574 outputs.
Actual timing, output equality, other bindings actions and full browser
validation remain required. Experimental branch only; no production rollout.
