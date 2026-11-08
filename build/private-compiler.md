# Private compiler dependency input

BuildBuddy's managed workflow auth can fetch the prepared compiler archive from
its existing CI artifact store. The private handoff probe at `f70d82a` passes.
No public release is required for this experiment.

`bb_cold --trained-compiler` fetches exactly the pinned 39,193,174-byte archive
into the permitted dependency-download cache. It checks SHA256 even on reuse;
corrupt cached files fail. Fetch and verification time count in the cold clock.
This fetch reads one compiler dependency archive, not Chromium action results.
The archive contains the same 365 entries as upstream; only `bin/llvm` differs.

`local_cold --compiler-archive` accepts that explicit verified input. After a
fresh git archive checkout, it derives a root LLVM index from the committed
upstream 0.8.26 index. Only the Linux AMD64 compiler archive entry changes.
A generated root MODULE declaration selects this index through LLVM's supported
index API. Generated index/module hashes are recorded; Chromium source and
compiler flags stay intact. This is declared build configuration, not reuse of
an extracted compiler repository. The archive is extracted into fresh Bazel
state. Successful builds must also match the actual compiler binary hash.

Fresh install/output/user state and auxiliary caches remain mandatory. RBE,
action, disk, remote and repository-contents caches remain disabled. Checkout,
configuration, archive fetch, compilation, packaging and artifact copies count.
LLVM source preparation remains separate, like preparation of upstream prebuilt
toolchains; it does not occur inside this trial.

This is an experimental Linux AMD64 protocol. Full cold timing, complete browser
payload, ABI and rendering validation remain pending. Other four triples' cold
timings remain unmeasured. Default builds retain the published compiler.
