# Upstream standard PCH experiment

Experimental Linux amd64 targets only. Browser defaults stay unchanged.
Upstream disables Linux PCH because it was slower; measure before rollout.

The trained compiler's Blink trace spends 2.67s of 2.70s in its frontend.
Instrumented object bytes match the sandboxed baseline. An initial eight-source
direct ABBA pilot saves 7.1% wall time and 5.9% CPU including PCH preparation;
all 32 objects match. This direct pilot did not exercise independent sandboxes.

The corrected sandboxed prototype matches all 256 original object hashes and
the complete cohort archive. Actual compiler SHA256 is verified. This proves
cohort correctness, not a timing or complete-browser improvement.

The PCH imports fixed upstream `build/precompile.h` through hermetic toolchain
include paths. Project include paths otherwise pulled Crashpad's `signal.h`
into the PCH, creating an undeclared consumer dependency. Project include
options in the producer are rejected. Consumer flags and inputs stay intact.
Consumers also declare the original upstream header.

Clang's documented `--relocatable-pch` with `-isysroot .` makes PCH paths relative
to each sandbox. Both benchmark variants use that explicit sysroot; corrected
PCH objects still match the original baseline without it. Compiler validation
stays enabled. No host headers or prior-build PCH reuse.

The BB harness fixes CPU capacity/job count, 14GB action memory, 8g JVM and a
private 8GiB RAM sandbox. Warm both variants, then ABBA. Each measured pass must
execute exactly 256 local compiles; each candidate rebuilds one PCH. Supporting
Python/compile work must not rerun. Exact consumer flags/environment must match
after removing the explicit PCH input and output paths. Objects and archive
must match too. This remains a warm benchmark, not strict-cold proof.

The first BB attempt failed before compilation: analysis had not materialized
execroot repository links. Compiler verification now reads the fetched repository
path directly. Regression reproduces that failure, then passes after the fix.
186 Python tests and actual 256-command/inventory/compiler preflight pass.

Remaining gates: fixed-resource BB timing, complete browser payload, ABI/rendering
and strict-cold duration. Other four triples' strict-cold timings remain unmeasured.

Both initial timing reports were rejected: BEP counted all 256 compiles, but slim
profiles omitted individual action/subprocess detail. The harness now requests
`--noslim_profile`; a real recompile of the previously omitted source records
its local subprocess and preserves object bytes. Execution and byte guards stay
strict. Full ABBA must rerun before accepting any speedup.
