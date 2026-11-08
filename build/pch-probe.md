# Upstream PCH experiment

Not enabled in browser builds. Linux upstream disables PCH because it was slower.
Measure current toolchain before adopting it.

The trained LLVM compiler spends 2.67s of a 2.70s instrumented Blink compile in
its frontend. Diagnostic object bytes match the sandboxed baseline. This one
source enters 2,475 files and tracks 1,604 headers; backend time is 0.007s.

A direct eight-source ABBA pilot uses Chromium's unchanged `build/precompile.h`
and the exact trained compiler/context. All 32 objects match sandboxed baseline
objects. Candidate phases rebuild their PCH: mean wall time falls 32.70s to
30.38s (7.1%); compiler CPU falls 32.21s to 30.32s (5.9%). This is warm diagnostic
evidence, not a cold or complete browser result.

The Bazel prototype declares its header, compiler, full header context, extra
inputs, PCH and dependency file. Consumers declare the PCH as a compiler input.
No host compiler, validation bypass or prior-build PCH reuse. Only experimental
Linux amd64 probe targets use it. The upstream header export adds no default
actions.

Next gates: real sandboxed PCH and 256 compiles, expanded command/context
comparison, matching all objects/archive, then fixed-resource ABBA including
fresh PCH preparation. Full browser payload, ABI/rendering and strict-cold
timing remain mandatory before rollout. Other four triples remain unmeasured.

The first sandboxed PCH generation succeeds (29.58s command elapsed with warm
support; 15.53s critical path). Consumers remain unverified. A mismatched RTTI
consumer correctly fails Clang's PCH compatibility checks. No validation bypass.
An incorrect-workspace consumer attempt was discarded; subsequent repository
state proved inconsistent. Consumer validation now uses a separate fresh
source/install/output/user fixture; saved baseline object hashes remain intact.

The BB harness uses CPU capacity as both CPU budget and job count, 14GB action
memory, 8g JVM and a private 8GiB RAM sandbox. Warm both variants, then ABBA.
Every measured pass must execute exactly 256 local compiles; each candidate
rebuilds one PCH. Supporting Python/compile work must not rerun. Compare exact
compiler flags/environment after removing the explicit PCH input and output
paths. Reject different macros, include order, compiler binary or object/archive
bytes. This remains a warm benchmark, not strict-cold proof.
