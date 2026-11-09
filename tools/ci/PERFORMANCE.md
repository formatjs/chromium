# Chromium build performance

Optimize measured compiler work first. Keep compiler flags, target ABIs, and
artifact smoke coverage intact. Compare the same workload and cache state;
registered actions are not executed compiles.

## Local cold-build target

Target: complete local Chromium archive under one hour, reusing only fetched
dependency archives. Each proof run needs fresh output, install, extracted
repository and auxiliary tool state; no action cache or remote execution.
Keep hermetic toolchains, sandboxing, compiler semantics and artifact checks.
Start with Linux AMD64; report other triples separately.

Current host has a 16-CPU quota, 48GiB RAM and EBS-backed ext4 storage. Changing
hardware starts a separate comparison. OS page cache and upstream HTTP caches
remain uncontrolled. Checkout/setup, analysis, generators, compilation, linking
and packaging count toward elapsed time.

The first uncached local baseline was cancelled at 86m08s after the new one-hour
goal was set. It executed 23,987 C++ actions with zero cache hits and no RBE.
It did not produce an archive; this is a failed target, not a completed build
time. The sampled bottleneck was storage: roughly 73% I/O full stall, low CPU
use, and compiler/Bazel threads waiting on ext4 journal operations. Short spans
were coalesced in its profile; BEP metrics give actual executed action counts.

Local compiler probes compare unchanged captured contexts in repeated
baseline/scanner/scanner/baseline order after warmups. Every selected compiler
must execute locally, archives must match, and compact logs must cover every
input comparison. Supporting setup stays warm; these probes are not cold-build
proof. Raw logs stay local.

```sh
python3 -m tools.ci.compile.local \
  --directory /tmp/chromium-local-inputs \
  --repository-cache /path/to/download-cache \
  --bazel /path/to/bazel-9.2.0 \
  --bb /path/to/bb
```

An independent `--comparison=inmemory-sandboxes` trial measures Bazel's
[in-memory sandbox bookkeeping](https://github.com/bazelbuild/bazel/blob/9.2.0/src/main/java/com/google/devtools/build/lib/sandbox/SandboxOptions.java#L292).
It must preserve compiler inputs and archive bytes. No production change or
speedup is claimed before measurements pass.

The 16-source include-scanning probe completes in 61/57 seconds without scanning
and 20/21 seconds with scanning. Each comparison removes 514,492 input paths;
all three archives match, including the unpatched-toolchain reference. LLVM's
header providers must expose individual files while preserving separate source
directories for resource copying. Otherwise discovered headers collide with
directory inputs in local sandboxes. Compiler versions and flags stay unchanged.
Only compiler resource, glibc and kernel header sets opt in; SDK consumers keep
their existing single-directory contract.

A separate RAM-sandbox probe takes 61/75 seconds on ext4 and 20/19 seconds on
tmpfs. Both input comparisons contain zero changes; every archive matches.
These are isolated compiler probes, not complete cold-build timings. The tmpfs
is empty, private, bounded to 16GiB and removed on namespace exit. Builds retain
their UID and run without setup capabilities. Source extraction and final
outputs remain on ext4; sandbox contents consume the same 48GiB memory budget.

Run the complete benchmark from a committed candidate:

```sh
python3 -m tools.ci.compile.private_ram --size-gib 16 -- \
  python3 -m tools.ci.local_cold \
  --directory /tmp/chromium-local-cold-new \
  --repository-cache /path/to/download-cache \
  --revision FULL_COMMIT_SHA --bazel /path/to/bazel-9.2.0 \
  --sandbox-base '{sandbox}' --max-seconds 0
```

The report verifies fresh Bazel roots, explicit cache disabling and real local
sandbox execution. Its timer includes private sandbox setup, checkout, fetch,
analysis, compilation, linking, packaging and artifact copying. A successful
archive still needs ABI, rendering and payload comparison before accepting
the optimization. Each new cold trial needs a new directory.

The original RAM-sandbox baseline at `4ad4231` finishes in 12,940.10s
(3h35m40s), executing 75,286 C++ actions locally with no reused action results.
No OOM kills occur. Its archive fails relocation: local sandbox input symlinks
were stored as absolute archive links. The packaging fix materializes those
files while preserving relative framework links. A separate repack of the same
compiled output passes ABI and both rendering pages with zero changed pixels;
this repack is correctness evidence, not a replacement cold timing result.

## Strict BuildBuddy cold target

Target: complete Linux AMD64 archive under one hour on a BuildBuddy workflow
runner. `perf/strict-cold-*` requests 16 CPUs, 32GiB RAM and 200GiB disk;
the report records actual CPU and memory limits. BB rejected the initial
32-CPU request and then 48GiB request: this organization permits at most 16 CPUs
and 32GiB per workflow runner.
Storage and CPU model can still differ from the local baseline. Other triples
are not measured yet.

`tools.ci.bb_cold` runs the local protocol with a verified direct Bazel binary,
fresh checkout, install/output roots and auxiliary caches. RBE, action caches,
disk caches and extracted repository caches are disabled. Only fetched archives
can persist between trials. A private 8GiB tmpfs holds sandbox bookkeeping;
outputs and extracted sources stay on disk. Runner VM snapshots and OS page
cache remain uncontrolled; no claim of physically cold RAM or storage.

The outer timer includes Bazel download, private sandbox setup, fresh source
checkout, fetch/extraction, analysis, generation, compilation, linking, packaging
and copying artifacts into the BB handoff directory. The workflow service's
initial repository fetch/queue time is outside this timer, matching the existing
local protocol's use of fetched Git objects. Profile summarization and runner
cleanup happen afterward. Publish cache-policy proof and a sanitized profile;
accept only after the exact archive passes native ABI and rendering checks.
Acceptance also requires the full BB workflow duration below one hour, covering
the service's checkout and setup before the benchmark process starts.

The native tool sharing experiment at `ff7cee3` reduces the analyzed full archive
closure from 76,719 to 52,534 C++ actions (24,185 fewer, 31.5%). The disabled
prototype preserves the original C++ action fingerprints; enabled sharing
requires an execution toolchain marker for Linux AMD64 GNU 2.31, and the probe
verifies missing registration fails. Configurable and external tools keep their
execution transition. These are action counts, not executed compile timings.

The normal Linux AMD64 workflow enables sharing with `--native-tools`.
Browser compiler/toolchain settings stay unchanged; native tools use the matching
target configuration. The full validation build at `11eb009` matches `9c52255`
byte-for-byte across all 5,176 payload members, and passes native ABI/rendering
smoke. Its cache-enabled timing is not cold evidence. Cross builds retain the
default behavior; their strict-cold timings remain unmeasured.

New trials stream an uncompressed `cold-profile.json` into BB's artifact
directory so a hosted hard timeout can retain completed trace events. Raw BEP
and command files stay private. GitHub's collector sanitizes the trace; partial
profiles remain diagnostic and cannot pass the cold-result or timing gates.

No successful strict BB build is recorded yet. Prior RBE results below do not prove this
target. Hosted timeout limits can terminate a run before the configured 6h.

The strict baseline at `c871de7` reaches the hosted one-hour cap without an
archive. Workflow execution metadata records 54,990.8 CPU-seconds and
14,011,092,992 peak memory bytes. It is a failed timing target, not a completed
cold result. Its older harness did not retain a final profile or report.

The native-sharing trial at `2b0d5b5` also reaches the hosted one-hour cap
without an archive. Execution metadata records 55,663.4 CPU-seconds and
17,012,338,688 peak memory bytes. These incomplete runs cannot establish the
candidate's full-build speedup. Neither trial produced an artifact for validation.

The private-include prototype is rejected. Fully expanded compiler arguments
show 585 search entries per Gin compile before the change and 599 afterward.
All three probe archives match across six executions, but the proposed pruning
does not occur. Whole-build probe times also include inconsistent supporting
recompilation, so they cannot support a speedup claim.

Removing captured header-only include exports also fails the same gate:
585 search entries become 595. Keep both include prototypes disabled.

Six instrumented V8 compiles at `196079e` spend 126.69s in Clang's frontend
and 34.20s in its backend, out of 161.13s compiler task time. Instrumented and
uninstrumented archives match exactly; `-O3` and `-g0` remain unchanged.
The runner reports AMD EPYC, 11 CPUs in its affinity mask and 35,264,466,944
memory bytes after an 8-CPU/32GiB request. These selected compiles indicate
repeated parsing as the next investigation; they do not establish a whole-build
frontend percentage. Nested Clang timing totals must not be added together.

The separate generator scratch pilot at `89604ec` completes six executions of
the 5,574-file Blink bindings generator. Every generated byte matches. Measured
ABBA action times are 286.37/304.45s for disk scratch and 279.93/277.29s for
execroot scratch: 5.7% lower mean action time in this small sample. Both modes
use the same bounded 8GiB RAM sandbox; only the generator's staging directory
changes. This is warm supporting setup, not a full cold-build speedup. Keep the
change opt-in pending full-browser payload and rendering checks.

## BuildBuddy execution target

Target: under one hour per supported triple on BuildBuddy, including artifact
packaging. Preserve hermetic toolchains, declared inputs, compiler options,
target ABIs, and native rendering smoke coverage. All five workflows with fresh client state at
`85f68a7` finish in 35m01s–44m40s. All five exact artifacts pass native rendering
and payload checks; Linux ARM64 needs one unchanged-artifact native retry,
described below. The `24375b5` cohort finished in 35m56s–46m04s and passed native
rendering, but retained BuildBuddy's managed output base. Those timings are
uncached-action measurements, not fresh-output cold proof. The user's observed build effort, including retries, is about
2.5 hours; the mixed-cache profile below is not a cold baseline.

Measure with fresh Bazel output state and action-cache reuse disabled. Record
repository/download cache state and shared RBE CAS conditions; a fresh client
does not make the remote CAS cold. Report fetch/setup, analysis, execution,
linking, and packaging separately, plus total elapsed time and retries. Do not
sum overlapping profile spans as wall time. Confirm executed compiler counts
before calling a run cold.

Audit correction: BuildBuddy injects `startup --output_base` through its managed
RC. Setting `--output_user_root` alone did not isolate the output base. All earlier
trials retained repository/output state, even when compiler actions re-executed.
The replacement sets both paths explicitly and requires canonical BEP startup
options to confirm the expected output base was used and was absent before the
build. Cache counters alone cannot verify fresh state.

The corrected `95086b7` trials verify distinct temporary output bases from actual
canonical startup options. Windows AMD64 finishes in 39m40s, Linux AMD64 in
41m08s, Windows ARM64 in 42m19s, and Linux ARM64 in 48m43s. Their reports verify
fresh state and zero reused actions. Windows AMD64 also has 55,019 distinct,
completed, unmerged compiler executions in RBE metadata. Both Windows payloads,
including PDBs, match same-commit cached builds byte-for-byte after the provenance
fix. Darwin did not finish. Later bounded-mode executions also repeat successfully,
so a generator-pool failure is not established as the cause.

The initial scanner candidate left a host gap: Linux ARM64's browser capture contains
19 host Blink-core libraries with 2,733 source entries outside the dedicated
Blink-core macro. The follow-up covers captured host core, modules, platform,
and bindings: 162 libraries with 7,604 source entries. Full Linux ARM64 cold
compilation passes at `85f68a7`. The other four browser captures contain no Blink-core libraries.

The hosted build command accepts `--cold`. It starts a batch Bazel process with
a unique output root and fresh repository download cache, disables disk caches
and remote action-cache reads, and writes `cold-build.json` when Bazel returns, including build failures.
The hosted hard timeout can terminate the process before that report is written.
Successful results require actual C++ executions, complete cache metrics, and
zero observed action-cache hits. Cold runs also apply Bazel's `no-cache` execution
policy: BuildBuddy [disables in-flight merging for uncached actions](https://github.com/buildbuddy-io/buildbuddy/blob/master/enterprise/server/remote_execution/action_merger/action_merger.go#L238).
Skipping cache lookup alone does not prevent merging. Instance names do not
isolate the merger either. This policy changes neither compiler options nor
inputs; action results are not cached, while CAS remains available. Elapsed time
includes artifact copying but excludes temporary-directory cleanup.

Each `perf/cold-<platform>` branch triggers only that platform's cold browser
job. The first Linux AMD64 calibration predates the explicit `no-cache` policy
and overlaps other validation; it is not final isolated cold proof. Later matched
concurrency comparisons should run after other compiler workloads finish.

Hosted free-tier workflows have a one-hour cap even with `timeout: 6h` configured.
All five initial full-browser candidate workflows hit that cap at exactly 3,600
seconds without compiler errors. Resuming their cached work validates artifacts;
it does not establish a cold-build result.

The first four isolated cold runs at `ce310d1` (8 client CPUs, 64 jobs,
retained trees) also hit that cap without compiler errors. Final action progress
was 142,247/161,470 Linux ARM64, 122,649/127,570 Darwin ARM64,
114,565/122,379 Windows AMD64, and 117,489/124,685 Windows ARM64. These counts
include internal and generator work; they do not predict remaining compile time.
Their killed Bazel children emitted no final profile or cold-result report.

The wider Linux AMD64 cold trial at `5bfb3df` also hit the cap at
145,437/154,750 actions, without compiler errors. Progress is not a finish-time
estimate. Cold runs write an uncompressed profile directly into BuildBuddy's artifact
directory, preserving partial timing after a hard kill. Raw BEP stays temporary
because command-line events can include authentication headers. Incomplete profiles are diagnostic only; successful cold proof still
requires complete final metrics and zero action-cache hits. Raw files stay on
BuildBuddy; GitHub receives sanitized summaries only.

The initial Linux AMD64 calibration also hit the one-hour cap. The next isolated
run requests 16 client CPUs instead of 8, retaining 64 remote action slots and
the existing memory budget. This tests the client input-processing bottleneck;
it is not yet a demonstrated full-build speedup. That 16-CPU run at `0248ef2`
also hit the one-hour cap: 142,837/154,750 actions, no compiler errors, and no
final cold report. The next matched trial compares 64 and 128 jobs with 16 client
CPUs, scanning, retained trees, and fixed compiler options.

## RBE results with fresh client state

The `85f68a7` cohort uses fresh output bases verified against canonical Bazel
startup options, fresh repository download caches, zero reused actions, and
no in-flight action merging. Shared RBE CAS and worker caches remain uncleared.
Times cover the complete BB workflow, including setup, fetching, analysis,
linking, packaging, and artifact upload.

These timings do not prove a dependency-cache-only cold build. RBE retained
shared CAS contents and worker state. An action-key salt can force misses
without clearing that state; an arbitrary shell variable might not enter action
keys at all. The local protocol above disables RBE and
all action caches; running it on a fresh BB runner would measure the same cache
conditions. A comparable RBE trial needs independently empty CAS and executor
state, not merely a new instance-name string.

| Target | Complete BB workflow | Executed C++ compiles | Executed Bazel actions |
| --- | ---: | ---: | ---: |
| [Darwin ARM64](https://formatjs.buildbuddy.io/invocation/7c86d092-f531-42dd-85bb-ee233cff840a) | 35m01s | 54,966 | 127,570 |
| [Windows MSVC AMD64](https://formatjs.buildbuddy.io/invocation/c1c6e279-e7f1-4ab4-9c1d-82be3547a9c7) | 37m08s | 55,019 | 122,379 |
| [Windows MSVC ARM64](https://formatjs.buildbuddy.io/invocation/aec72430-d18a-4447-9626-d583b1be45a2) | 39m00s | 55,764 | 124,685 |
| [Linux AMD64](https://formatjs.buildbuddy.io/invocation/efe51a1b-306d-4ba3-9754-8a4efedc0ba0) | 40m08s | 75,286 | 154,750 |
| [Linux ARM64](https://formatjs.buildbuddy.io/invocation/77be5395-5ac1-442c-aad5-839ef004ecff) | 44m40s | 77,537 | 161,470 |

Independent RBE metadata confirms all 318,572 distinct, completed, unmerged C++
outputs, with no failed or incomplete compile records. The workflows execute
690,854 Bazel actions in total. All builds run on Linux AMD64; four targets are
cross-compiled. GHA target machines only execute downloaded artifacts.

All five exact cold artifacts pass native ABI and rendering smoke. Darwin and
Windows payloads, including PDBs, match same-commit normal builds byte-for-byte.
Both Linux comparisons verify the existing randomized NSS signatures while
covering every other tar byte. Exact-artifact evidence:
[Linux AMD64](https://github.com/formatjs/chromium/actions/runs/42384803347),
[Linux ARM64](https://github.com/formatjs/chromium/actions/runs/42385204450),
[Darwin ARM64](https://github.com/formatjs/chromium/actions/runs/42384394363),
[Windows AMD64](https://github.com/formatjs/chromium/actions/runs/42384568172), and
[Windows ARM64](https://github.com/formatjs/chromium/actions/runs/42384716677).

Linux ARM64's first native attempt captures repeated page content in the layout
scene's bottom rows: 1,456 pixels exceed tolerance. The same artifact and harness
pass on retry with zero changed pixels in both scenes. The failed evidence stays
available. A [native differential probe](https://github.com/formatjs/chromium/actions/runs/42385696912)
passes 60/60 unchanged captures; an explicit-viewport candidate fails 4/60.
Reject that candidate. The original harness and strict thresholds stay intact;
the intermittent capture issue remains a known limitation, not a diagnosed
compiler regression. Neither baseline nor comparison thresholds changed.

Final profiles report 3m38s–4m05s analysis and 29m42s–39m20s execution; critical
paths are 6m24s–9m44s. Mean Bazel CPU usage is 7.7–10.9 cores, sampled heap peaks
are 9.4–10.4GB, and average active actions are 95–113. Sampled worker queues
average 61–80ms. These are overlapping spans, not additive wall-time savings.
Per-library attribution covers only paired same-thread spans; use complete RBE
execution records for compiler counts. Darwin's final framework action takes
155s, including 121s downloading inputs. Moving that link to RBE is a future
measurement candidate, not part of this change. All current toolchains and
compiler options stay intact.

The earlier `0046328` cohort already verified the four Linux/Windows targets in
39m20s–47m36s, including exact-artifact smoke and payload checks. Darwin failed
there; the latest clean-runner cohort supersedes that incomplete result.

Darwin's `0046328` run repeatedly executes the same bindings action. Eight
executions complete successfully in roughly 3m30s each; this is not evidence of
a stuck generator or an OOM. The bounded upstream mode preserves output bytes,
but does not resolve this repeated work. An isolated `41b2719` trial uses Bazel
9.3.0 and enables input-recovery messages. Its full Darwin analysis passes, but the build then reports no space left on
device. The trial does not establish a rewinding fix. Both 200GB and 400GB disk
requests expose the same 93GiB filesystem; /tmp and workspace share that device.
Moving paths alone cannot resolve the capacity issue. A separate 03d46f1 trial
uses a fresh runner namespace with Bazel 9.2: 87GiB free and no managed output
base at startup. That diagnostic finishes in 35m39s, passes native rendering,
and produces a byte-identical Darwin payload. The final `85f68a7` run also executes
bindings once successfully. Bazel 9.3 includes
[upstream rewinding fixes](https://github.com/bazelbuild/bazel/releases/tag/9.3.0);
a connection to the earlier repeated work remains unproven. Production stays on
Bazel 9.2; no compiler or toolchain change is needed for the measured results.

Cold jobs now use distinct clean-runner namespaces. Retry state lives in an
owned scratch directory outside the checkout; a later run removes abandoned
build directories after verifying ownership. Unmarked directories, symlinks,
and unexpected files are rejected. Each build still gets a unique output base
and repository cache, with canonical startup and zero-reuse checks. Reports
include actual filesystem bytes and inodes before and after the build, not a
peak estimate. The 200GB YAML request does not imply 200GB was provisioned.

## Baseline

[Linux ARM64 compile-heavy profile](https://formatjs.buildbuddy.io/invocation/97238e03-06be-49ad-abed-4699731fe294):

- 57m32s wall time; 49s analysis, 56m35s execution.
- 18,337 remote executions; 16,589 remote cache hits. Mixed cache, not fully cold.
  This run failed at the snapshot-generator link, so it is not a successful
  browser build-time estimate.
- 17,849 recorded C++ worker spans. Blink accounts for 8,852 spans and 55,293
  worker-seconds; 8,833 Blink spans compile host tools.
- Merkle construction: 27,533 concurrent task-seconds. Client CPU averages 10.54
  cores; worker queue time is small. These sums overlap and are not wall time.
- Slowest recorded compiler: `layout_box.cc`, 86.1s worker time.
- Current representative Blink action declares 76,130 inputs; compilation
  context exposes 74,982 headers.

Completed mixed-cache code builds at `2b28ee4` confirm the same client limit:

- [Linux AMD64](https://formatjs.buildbuddy.io/invocation/5f633002-2541-4944-b9ce-61b57ce39b18):
  Bazel 44m10s; 40,895 remote cache hits and 5,818 real remote actions. Client CPU
  averages 10.30 cores. Merkle construction totals 22,776 task-seconds.
- [Windows AMD64](https://formatjs.buildbuddy.io/invocation/8a5cb9ab-a606-4d86-9d5c-1f378630ee30):
  Bazel 38m43s; 28,026 remote cache hits and 3,665 real remote actions. Client CPU
  averages 9.26 cores. Merkle construction totals 18,692 task-seconds.
- Matching local Merkle spans to their owning compile spans attributes Linux's
  largest sums to Chrome (7,921 task-seconds), components (3,276), and Blink
  target/host (6,414 combined). Windows Chrome contributes 7,963 task-seconds.
  These overlapping sums are not wall-time savings. A 13-source Chrome,
  extensions, and component probe targets the next scope; production remains
  gated on repeated archive equality and full browser validation.

## Order of work

1. **Reduce compiler inputs.** The isolated Blink probe uses the real compilation
   context and compiler options. Compare compact execution logs, compiler-only
   timing, and archive hashes. Include scanning needs both its Bazel flag and
   requested feature. If this reduces inputs, repeat representative compiles,
   then validate all five browser builds and native rendering smoke tests.
2. **Share host objects through a narrow dependency seam.** Confirm compiler,
   defines, headers, ABI, and link dependencies match. Measure the complete host
   closure before rollout. Avoid aliases that import additional native closures.
3. **Tune client resources and concurrency.** After input work, compare fixed
   compile workloads at different client CPU allocations and action concurrency.
   Record wall time, client CPU, heap, GC, and actual remote executions. Increasing
   remote concurrency alone does not fix client input-processing saturation.

Also audit include-directory propagation. The representative core target has
14 captured include directories but resolves 945 search entries through its
dependency context. Captured target-local directories may belong in local
compiler options rather than public `includes`; validate header selection and
object equivalence before changing that boundary.

## Earlier experiments

These notes record intermediate results. The final cohort above supersedes
their pending rollout and validation statements.

- The isolated 13-source browser comparison at `482a69c` passes all five
  triples: all four archive sets match per platform, 260 selected compiles total.
  Each pair removes 1,307,001 input paths net on Linux AMD64, 1,315,256 on
  Linux ARM64, 1,282,159 on Darwin ARM64, 1,312,116 on Windows AMD64, and
  1,325,142 on Windows ARM64. These are input reductions, not full-build speedups.
  Discovery uses the captured Linux Wi-Fi, POSIX, or Windows source. An expanded
  14-source check adds the utility context exposed by full Linux validation.
- Native-scope Linux ARM64 at `186bf14` passes full artifact and rendering smoke.
  Its complete compressed payload matches `4a2321d` byte-for-byte: 314,287,421
  bytes, SHA256 `8fa250e8427cd63a70f0e58de13b9f4e4c7a2d20ee217485cc7b7e44575d56d0`.
  Darwin ARM64 and Windows AMD64 also pass full builds; Windows ARM64 reached
  compression before the workflow cap. These runs use ordinary cache settings.
- The Linux browser candidate now requests scanning for captured Chrome,
  extensions, and component libraries: 2,480 eligible library targets with 10,482
  C/C++ source entries. Its 13-source owner-context probe passes repeated archive
  equality. Executables and shared-library targets keep their prior selection.
  Full artifact, rendering, payload equivalence, and cold timing remain gated;
  all platform candidates still require full browser validation.
- Browser hotspot comparisons at `56c692e` now pass all four modes with
  identical archives after removing private protobuf shadows. The benchmark's
  next scanner switch selects the probe rules' feature locally, leaving support
  generators on production scanning. Real queries resolve the feature off/on,
  preserve all 13 probe compiler commands, and preserve 4,796 supporting C++
  action keys. The narrower six-source comparison also passes on all five triples: archive
  sets match and both pairs remove 0.421–0.443 million input paths net. This
  isolates the rule feature; the earlier global-flag comparison also varied
  supporting input setup. New scanner trials require positive net input reduction.
- Chromium, ipcz, and openscreen carry inactive protobuf headers. Excluding
  declarations alone leaves those files visible to local include discovery.
  Chromium/ipcz source projections hide the unused subtree; openscreen's pinned
  checkout now removes its unused copy. Restore openscreen's original quote
  paths: stripping them changed header selection, allowing compact_enc_det's
  `util/string_util.h` to shadow openscreen's own header. The browser probe now
  also covers `chrome/utility/services.cc`, found by full validation.
- The expanded utility probe reproduces a forwarding cycle through
  sentencepiece's `gtest/gtest_prod.h` shim. Full inputs had accidentally supplied
  `FRIEND_TEST` through AOM's bundled GoogleTest copy; scanning exposed the cycle.
  Chromium's forwarding headers now select the declared BCR
  `googletest/include/gtest/gtest_prod.h` directly. A real compiler replay of the
  utility include context fails before this fix and passes after it. Repeat the
  expanded probes before promoting the other browser scopes.
- Native 19-source comparisons now pass on all five triples at `9730c78`,
  including generated bindings and GPU/codec paths. All four archive sets match
  per platform, with complete selected-compiler diff coverage: 380 real selected
  compiles total. Each pair removes 1.303–1.372 million input paths net.
  The matching library scope now covers all native overlays: 138–139 libraries
  and 3,836–3,844 source entries per triple. Linux ARM64 inherits its module macro
  from the base overlay; the remaining platform-specific macros match that scope.
  Four platform artifact validations run separately while Linux AMD64's existing
  native-scope validation finishes. Cold timing and full artifact gates remain open.
- The browser hotspot scanner trial exposed a local/RBE mismatch: Chromium's
  unused vendored protobuf headers shadowed the canonical BCR forwarding headers.
  Chromium and ipcz projections now exclude `third_party/protobuf/src`; the shared
  source archive stays intact. No captured input labels use that directory:
  generators already declare canonical BCR protobuf inputs. A real 13-action
  query preserves every compiler argument after projection. Filesystem tests
  cover excluded subtrees, explicit overlay replacements, and archive preservation.
  Repeated browser archive validation remains pending.
- [64/128-job benchmark](https://formatjs.buildbuddy.io/invocation/93efbf69-445f-4732-a380-1a25e8761e81)
  passed two warmups and ABBA comparisons across 101 sources with 16 client CPUs,
  scanning, retained trees, and a 12 GiB heap. All archive sets match; input paths
  are unchanged. Execution was 43.19s/51.22s at 64 jobs versus 46.05s/52.02s at
  128 jobs. Both pairs were slower at 128; keep the production limit at 64.
  Other validations overlapped, so the result does not establish a universal
  concurrency optimum. The next cold Linux AMD64 trial combines the validated
  native scope with more client CPU. BuildBuddy rejected 32 CPUs before execution:
  this organization limits each runner to 16 vCPUs. The next cold trial keeps 16
  client CPUs, 32 GB memory, and 64 jobs while testing the wider native scope.
- [Native 19-source regression](https://formatjs.buildbuddy.io/invocation/7a4c660c-f4c6-4d06-9e54-1996c0eafbe6)
  passed baseline/scanner/scanner/baseline with identical archives using Linux
  AMD64's native library contexts. Both pairs removed 1,377,555 input paths and
  added 5,611: **1,371,944 fewer paths net**. The next candidate extends scoped scanning to
  its Blink modules, bindings, and platform libraries: 139 libraries and 3,841
  source entries. Mandatory macro-selected headers remain declared. Full artifact,
  native rendering, and cold timing gates remain pending.
- [101-source scanner benchmark](https://formatjs.buildbuddy.io/invocation/33661bf5-b986-4a93-9bbc-a49441f975b8)
  passed two warmups and ABBA comparisons: 606 real remote compiles, identical
  archive sets. Each pair removed 7,535,800 input paths and added 29,472:
  **7,506,328 fewer paths net**. Client CPU fell 18–24% in both pairs. Execution
  phases were 95.22s/50.18s baseline versus 46.04s/42.15s scanner; worker load
  differed, so these are not a full-build speedup estimate. Sampled heap did not
  increase. Merkle construction fell from 73.51–91.76 to 5.95–8.07 task-seconds.
- [19-source host regression](https://formatjs.buildbuddy.io/invocation/f6a8f4a1-e78a-4b97-8b3e-6ba2515a3587)
  passed all four modes after full ARM validation exposed generated-header and
  codec include issues. The fixes declare the real GPU header producer and a
  directly included base header. Public AOM adapters remove private quote roots
  that shadow canonical libyuv headers; public includes and linking stay intact.
  Coverage includes generated permission strings, V8 bindings, WebRTC, WebCodecs,
  GPU bitmap paths, accessibility, canvas, and WTF.
- Four full candidate browser artifacts and native rendering smoke tests pass
  at `2b28ee4`: Linux AMD64, Darwin ARM64, and both Windows MSVC targets. Windows
  AMD64's complete compressed payload matches baseline `4a2321d` byte-for-byte
  (1,509,377,784 bytes; SHA-256
  `94b07618f1bae1e5d9ebd9fc8b6875ba08f29ced16f20e6ea95bb3b72c4ebfb8`).
  Linux ARM64 failed on the header cases covered by the 19-source regression;
  its full validation rerun remains pending. These builds reuse cached work and
  do not establish cold-build timing.
- [Matched input-tree retention benchmark](https://formatjs.buildbuddy.io/invocation/69e0a9ba-41b7-4b9c-adf1-50415c043bf3)
  passed two warmups and ABBA comparisons across 101 sources. All six archive
  sets match; every selected compile executed remotely. Retention changed zero
  input paths. Execution phases averaged 51.19s baseline versus 45.16s retained
  (12% lower); client CPU averaged 408.28s versus 380.11s (7% lower). Both paired
  execution comparisons improved. Peak sampled heap rose from 3.57 GB to 4.54 GB.
  Hosted browser builds retain trees with a 12 GiB JVM heap budget inside the
  existing 32 GB runner. Shared worker load limits extrapolation to full builds.
- [Wider host Blink trial](https://formatjs.buildbuddy.io/invocation/f01535b3-73c1-44af-8d5c-89409df45244)
  passed all four runs with identical archives across 12 sources, including
  accessibility, canvas, WTF, and generated V8 bindings. Both pairs removed
  1,255,557 paths and added 3,663: **1,251,894 fewer input paths net**. Warm execution
  times stayed near 34s. Compiler worker timing needs interval overlap: remote
  timestamps can extend milliseconds beyond the client action interval. Strict
  containment incorrectly reported zero worker time; a regression covers this.
- [Host Blink-core differential trial](https://formatjs.buildbuddy.io/invocation/a20cde7e-eea3-453d-9e31-4614451d0152)
  passed baseline/scanner/scanner/baseline with identical archives across six
  compiles. Both pairs removed 633,206 input paths and added 1,883: **631,323
  fewer paths net**. Warm execution times were 25.8s baseline and 26.6s/28.1s
  scanner. The first baseline also ran 2,218 generator actions and spent time
  fetching repositories; its 354s wall time is not comparable. Header input
  reduction is proven; throughput improvement remains unproven.
- Payload compression now caches independently of revision stamping. A real
  Windows payload took 138.6s to compress; subsequent stamps took 5.7s and 1.3s.
  This improves packaging, not compiler throughput.
- Rejected host-Mojo sharing: 21 aliases removed 353 source entries locally but
  grew the full registered C++ graph from 83,734 to 84,278 actions. Reverted.
- First compact-log scanner comparison produced identical archives but zero
  input reduction. Compiler action times were 31.2s and 21.8s; one pair does not
  establish a speedup. The required feature was missing. Corrected pilot runs
  separately from production browser settings.
- Global scanner features broke hermetic LLVM's glibc bootstrap (`config.h`
  missing). The next pilot requests the feature only on its Blink probe; baseline
  still disables the scanner flag. Toolchain dependencies keep their existing
  feature selection.
- [Scoped single-source pilot](https://formatjs.buildbuddy.io/invocation/8520913d-1109-4677-aad6-3f3b69406c47)
  passed with identical archive bytes: 72,405 input paths removed, 338 added,
  **72,067 fewer paths net**. Macro-selected Skia headers and a directory needed
  by its relative include remain mandatory inputs. Action time was 27.0s versus
  23.6s; worker time 23.7s versus 22.6s. This pair does not establish a full-build
  speedup. The next experiment covers layout, view, and SVG paint sources in
  baseline/scanner/scanner/baseline order, forcing recompilation each time.
- [Repeated three-source benchmark](https://formatjs.buildbuddy.io/invocation/555bc229-3711-450c-9621-3fb29d9fec5e)
  passed all four runs with identical archive bytes. Both paired comparisons
  removed 219,959 paths and added 987: **218,972 fewer compiler input paths**
  across three actions. Whole-probe wall times were baseline 59.1s/45.3s and
  scanner 47.4s/44.1s. The first baseline also executed two extra remote actions;
  worker load was uncontrolled. Input reduction repeats; browser wall-time
  improvement remains unmeasured. Production scanning remains off until wider
  source and cross-platform validation passes.

The cross-platform archive pilot also passes on Darwin ARM64 with debug info
enabled: 208,487 paths removed and 486 added, or 208,001 fewer paths per comparison
across three actions. All four archive hashes match. The first Darwin attempt
exposed an unwanted dynamic-library link; probes now explicitly use static
archives, matching the owning Chromium libraries.

The full-browser candidate requests scanning for native Blink core libraries plus
the captured Linux ARM64 host core, modules, platform, and bindings. Known
macro-selected Skia headers remain mandatory inputs. Its rollout gate includes
all five browser artifacts, native rendering smoke, and the Linux runtime suite.
BuildBuddy profiles must distinguish include discovery and repository setup from
compiler worker time before claiming a wall-time improvement.

Keep raw profiles in BuildBuddy or local temporary files. GitHub artifacts carry
sanitized metrics only.

## Next concurrency measurement

The earlier 101-source comparison has a 40–50s critical path, close to its whole
execution phase; it cannot establish sustained full-build throughput. The next
fixed batch contains 960 common Blink-core sources that took at most eight
worker-seconds each in the `5bfb3df` cold snapshot, plus the existing core-probe
source. The sample belongs to all five captured core owners. Compare 64/128 jobs
with 16 client CPUs, identical scanning/retention, warmups, real executions,
complete input-diff coverage, and repeated archive equality. Record observed
worker sums and critical paths again; sample selection is not a speedup result.

Cold-profile collection also attributes completed Merkle, worker, and discovery
spans to containing compiler spans on the same thread, grouped by source family.
Processed compiler spans include cache checks; worker spans and BEP execution
counts establish actual execution. Unpaired spans stay in global totals. All
group durations are overlapping task sums. Raw names, arguments, and paths do
not enter the exported report. The same attribution reproduces Chrome's roughly
7,919 Merkle task-seconds in the earlier completed Linux code-build profile.

## Native browser scope rollout

After the expanded 14-source probes pass on the four cross targets, enable
scanning for native Chrome, extensions, and component libraries there. Scope
counts are 2,472 libraries / 10,436 C/C++ source entries on Linux ARM64,
2,828 / 10,421 on Darwin ARM64, and 2,565 / 10,741 on each Windows target.
Captured Linux host libraries keep their previous scope; executables, shared
libraries, and Objective-C helpers retain their existing settings. The new
`perf/browser-platform-rollout` branch validates all five browser artifacts.
These captured counts are not executed compiler counts or timing results.

The larger concurrency warmup executed 961 selected C++ actions, but the default
profile omitted one 61ms worker span. RBE execution metadata confirms that compile
ran. Benchmarks now request full profiler data and save diagnostic reports before
rejecting missing worker evidence. No timing gate was relaxed. Include-scanner
spans are reported separately from parent discovery spans to avoid double-counting.

Even full profiling omitted that short worker in the 128-job warmup. Execution
proof now requires one completed, unmerged RBE execution per selected source in
the same invocation. Missing, cached, merged, duplicate, and mismatched outputs
fail validation. Worker seconds come from execution metadata; profile worker
seconds remain separate for diagnostics. A real replay verifies all 961 compiles
from the first warmup, including the 0.061162s compiler.

The `1494feb` cold trial was intentionally cancelled before artifact upload after
a local test showed raw BEP retains remote authentication headers. Artifact audit
confirms zero raw event artifacts uploaded. Its partial run is not a timing result.
The replacement at `d49c868` keeps raw BEP temporary and persists only profiles
and sanitized metrics. No compiler or cache-policy change accompanies this retry.

## Compression measurement

Windows ARM64 previously reached compression before the workflow cap. A hermetic
Python benchmark now packages the actual Windows AMD64 bundle at gzip levels
6/1/1/6, recording wall time, CPU time, sizes, and compressed hashes. Every pass
must produce identical complete uncompressed tar bytes; repeated levels must
produce identical gzip bytes. The test bypasses caches and uses the existing
with_cfg Windows bundle. The full-bundle trial at `e684be3` measured level 6 at
388.83/403.12s and level 1 at 169.99/157.98s. Both levels produced the same
7,648,174,080-byte tar; repeated compressed hashes also matched. Level 1 saves
about 232s of packaging, growing the payload from 1,509,368,400 to
1,762,705,675 bytes (16.8%). Production now uses level 1; tar contents and
revision stamping stay unchanged.

The benchmark's test body passed, but Bazel's optional output zipper failed
because the worker lacked system `zip`. Disable zipped undeclared outputs and
read the declared report from the output directory instead. No host tool install.
The fixed harness passes at `24375b5`: level 6 takes 200.31/195.04s; level 1
takes 80.45/78.89s. Worker speeds differ from the first trial, but both show
roughly 60% less compression CPU time. Complete tar and repeated gzip hashes
match within and across both trials. Python 3.11.14 and zlib 1.3.1 are recorded.

Cold artifacts can also run native rendering smoke directly through the profile
workflow: select one platform, enable `smoke_cold_artifact`, and supply its successful
BuildBuddy workflow URL. The downloader verifies repository, full commit, cold
workflow identity, completion, and checksum before handing the archive to the
existing native smoke workflow. Cold smoke posts its own status. This also fixes
a cold-download filename bug that incorrectly selected the component prefix.

## Sustained concurrency result

The 961-source comparison at `13a2355` passes all modes: 5,766 real selected
compiles including warmups, identical archives, and zero input-path changes.
At 16 client CPUs, 64 jobs executes in 81.83/85.58s; 128 jobs takes 53.21/54.15s,
about 36% less. Critical paths are 19–25s, below the execution phase. Observed
mean worker execution rises from 46–48 concurrent workers to 70–74. Heap peaks
are 3.4–4.9GB within the 12GiB heap budget.

The hosted candidate now uses 128 jobs; local defaults stay unchanged. Validate
all browser artifacts, native rendering, payload equality, and full cold timing
before promoting it. The `d49c868` 64-job cold control hit the one-hour cap at
150,559/154,750 actions. Its preserved profile is incomplete, not cold proof.
The `perf/cold-linux-amd64-128` branch starts the follow-up without replacing it.

The expanded 14-source browser comparisons at `1494feb` now pass all five triples
with identical archives in all modes. Net paths removed per pair: Linux AMD64
1,408,793; Linux ARM64 1,417,683; Darwin ARM64 1,381,646; Windows AMD64 1,413,986;
Windows ARM64 1,428,014. Linux AMD64 at `9cb5359` also passes full browser and
native rendering validation. Cross-platform full validation remains in progress.

## NSS integrity-file variation

The full Linux AMD64 payload comparison at `9cb5359` finds identical binaries,
resources, tar metadata, and member order. Only four NSS `.chk` files differ;
the compressed payload changes by two bytes. NSS 3.61's original signer creates
a fresh DSA key and signature per invocation. This predates the performance
changes; [upstream tracks the same reproducibility issue](https://bugzilla.mozilla.org/show_bug.cgi?id=1902078).

An explicit `--verify-nss-integrity` comparison mode verifies every integrity
file against its exact module SHA-256 with pinned cryptography. Both artifacts
must retain identical DSA parameters. Whole-tar hashing then normalizes only
those verified file bodies; every other tar byte remains covered, including
metadata and ordering. Invalid signatures, changed modules, altered metadata,
and missing files fail. Default compressed-byte equality stays unchanged.
Runtime signing and cryptographic checks remain unchanged.

## Full 128-job validation

All five builds and native rendering smoke tests pass at `6c9b871`. These are
warm builds (14.6–24.3 minutes), not cold measurements. Linux ARM64 and Darwin
payloads match `4a2321d` byte-for-byte. Linux AMD64 matches after verifying the
four existing randomized NSS signatures.

Both Windows payloads differ only in `chrome.dll` and its PDB. PE diagnostics
confirm every DLL byte matches except its 16-byte CodeView GUID; code, resources,
unwind data, and relocations are identical. PDB differences remain visible, and
the default payload equality gate stays strict. The diagnostics do not authorize
ignoring arbitrary debug data. Cold artifacts must also be compared with the
validated `6c9b871` outputs, whose build inputs match the cold candidate.

## Uncached-action cohort (not strict cold)

The five trials at `24375b5` combine 128 jobs with measured gzip level 1.
Each uses 16 client CPUs, 32GB memory, and a 12GiB JVM heap. Toolchains, compiler
options, ABIs, and native rendering tests stay unchanged.

| Target | Complete BB workflow | Executed C++ compiles | Executed Bazel actions |
| --- | ---: | ---: | ---: |
| [Darwin ARM64](https://formatjs.buildbuddy.io/invocation/b46d94df-3dd6-41c8-9ac7-f3cdb04b040e) | 35m56s | 54,966 | 127,570 |
| [Windows MSVC AMD64](https://formatjs.buildbuddy.io/invocation/55244f41-71c6-4117-80c0-7a0732ce22ce) | 38m38s | 55,019 | 122,379 |
| [Windows MSVC ARM64](https://formatjs.buildbuddy.io/invocation/ba0ba31d-81cf-4c97-9297-f6aa5a63694c) | 39m38s | 55,764 | 124,685 |
| [Linux AMD64](https://formatjs.buildbuddy.io/invocation/61e548c4-e2dd-4b0e-9801-936011f91e61) | 40m36s | 75,286 | 154,750 |
| [Linux ARM64](https://formatjs.buildbuddy.io/invocation/3d45f95a-cfb9-48d3-8777-7e2ffa4dc364) | 46m04s | 77,537 | 161,470 |

Times include workflow setup, any fetching, analysis, linking, packaging,
and artifact upload. Each report records zero reused actions, disabled remote
action-cache reads and in-flight merging. Its claim of fresh output state was
incorrect: the managed RC retained `/home/buildbuddy/workspace/output-base`.
Repositories and output state were shared with earlier runs. The cohort executes
690,854 actions, including 318,572 C++ compiles; all five exact artifacts pass
native ABI and rendering smoke. These remain useful compilation measurements,
but do not satisfy the strict cold goal. Shared remote CAS is also not cleared.

Cold profiles show 3m33s–3m58s analysis and 31m08s–41m16s execution. Critical
paths are 6m43s–10m55s, below execution time: aggregate throughput dominates.
Mean Bazel CPU usage is 7.5–11.3 cores; peak sampled heap is 9.2–10.7GB.
Sampled worker queues average 59–83ms. These spans overlap; task sums are not
wall-time savings. Increasing concurrency again needs a measured heap budget.

Linux and Darwin payload contents match the validated `6c9b871` outputs after
verifying existing randomized NSS integrity files where present. Both Windows
native tests pass; byte comparisons still flag only `chrome.dll`'s CodeView GUID
and its PDB. No comparison exception hides those differences. PDB stream
diagnostics find only two changed streams out of 39,954: the PDB GUID and
`unexpire_flags_gen.obj`. All other streams, including linker environment paths,
are identical. The upstream generator writes `sys.argv[0]` into a source comment;
our runner had supplied its random temporary directory. That changed the source
checksum and derived PDB GUID despite identical runtime code.

Invoke scripts and response files through stable paths relative to the staged
build directory. Keep temporary isolation and upstream generators intact. A real
replay of the pinned generator produces varying `.cc`/`.h` bytes before the fix
and identical `.cc`/`.h`/`.inc` bytes afterward. A regression exercises the same
provenance pattern across distinct execution roots. No debug data is stripped or
ignored. Final platform validation follows this hermeticity fix.

## Binding generator budget

The corrected Darwin trial stops dispatching C++ work while one bindings action
remains active. It produces 5,574 files. Upstream's `TaskQueue` sizes a process
pool from the executor host's CPU count, independently of the action budget;
its pool can wait indefinitely if a worker disappears. Pool resource pressure
is a hypothesis, not an observed OOM diagnosis.

[A separate probe](https://formatjs.buildbuddy.io/invocation/0c21dca6-b59c-4dca-9596-2cbb3f9b8aaf)
at `340cdb9` runs upstream `--single_process` and compares all 5,574 output hashes
with the cached parallel producer. Every file matches. Use that supported mode
for binding generation, keeping upstream code and output coverage intact. The
production action query confirms exactly one flag and the complete output set.
The first four fresh-state targets pass while Darwin repeatedly completes the
bounded producer. The final clean-runner cohort passes all five builds without
repeating bindings. Serial mode bounds resource use and preserves outputs;
it alone did not fix the earlier repeated work.

### Combined native PCH cold trial

`--project-pch --blink-pch --native-tools` routes the validated V8 base,
Content browser and module bindings candidates alongside core and core bindings.
Default compiler/archive actions remain identical. Enabled wrappers add no
original-owner compiles; all 3,450 added candidate compile commands stay unchanged.
The actual archive graph reaches six PCH producers and validators.

The full browser link keeps every flag and object order, replacing only 6,878
object paths. Every replacement matches its original object bytes. Actual
relink produces the original browser SHA-256:
`21089926f88ecf518a8e5d53fa367df8b1ea76967c5b0b59491a83a9edf19294`.
Supporting outputs are reused for this correctness check; no cold timing claim.
Reports: `/tmp/chromium-project-pch-integration-report.json`,
`/tmp/chromium-project-pch-graph-report.json`,
`/tmp/chromium-project-pch-browser-link/report.json`.
Linux ARM64 package loading, buildifier and 202 tests pass.

The next strict-cold trial requires all six producers and validators to execute,
in addition to existing fresh-state/local-sandbox/cache-policy gates. Missing
or extra PCH actions reject the result. It retains the same resource limits and
records an unslimmed streaming profile. No successful cold result yet.

### Compressed-profile strict-cold retry

The combined trial `0fefa722` fails after 2,616.91 protocol seconds with Bazel
exit 36 and a clipped sandbox output-copy error. Its wrapper then raises
`MemoryError` while eagerly reading the raw trace. Uploading that trace also
fails. No archive or passing cold timing result exists.

A fresh BB diagnostic with the same 16-CPU/32GB/200GB requests exposes
99,913,961,472 disk bytes. Workspace, `/tmp`, home and artifacts share one device.
That rules out moving temporary paths as a capacity fix. It does not prove the
failed VM's exact disk usage or output-copy cause.

The retry uses a standard compressed Bazel profile. Normal short-span
coalescing stays enabled; full BEP counts and compact execution logging remain.
Compiler options, six PCH producers, toolchains and cache policy stay unchanged.
The streaming collector preserves all metrics from the 1,022,314-event completed
reference and handles a 46,638,712-event compressed trace with 29,992KiB peak RSS.
Failure logs print before profile analysis. Wider UI output avoids clipping the
cause. Five-second samples record output/sandbox capacity, free bytes/inodes
and profile size. The report requires a complete code trace in addition to
existing fresh-state, actual-local-execution and six-producer/validator gates.
Profile analysis now counts in its elapsed time; the full BB workflow duration
remains the final one-hour gate. 212 tests pass. No timing success claimed yet.

### Generated V8 PCH candidate

246 of 248 generated V8 initializers share the same 73 opening includes. The
candidate precompiles that ordered prefix; two exceptions compile normally.
A declared action checks every eligible source's opening includes before the
producer runs. Existing content validation checks the pinned 1,099-header closure.

Direct recompiles preserve all 246 original opt-exec objects. A separate Bazel
sandbox gate preserves all 248 objects and the complete archive against the
unchanged target in the same configuration. Expanded consumer flags/environment
match after expected PCH additions. Archive SHA-256:
`92861f441c27d045b914fdd4276a33fdabfebbdc10d382bc0d3907141c8fb022`.
Comparing generated-source objects across fastbuild/opt-exec configurations is
invalid here: `__FILE__` embeds their different paths. The same-context gate
covers this, rather than rewriting paths or accepting object differences.

Three local sample files use 40.74 compiler CPU seconds without PCH versus
23.53 plus 8.47 for its producer. Shared-host feasibility evidence only; no BB
or whole-cold speedup claim. 215 tests pass. Full-cohort BB ABBA wiring forces
all 248 compiles, PCH producer, prefix check and closure check each candidate pass.

Component diagnostics request the public `archive` output group. Default
`cc_library` output selection also forces transitive dependency compiles, adding
about 1,429 unnecessary actions to this comparison's graph. Both variants still
produce the complete cohort archive. Final strict-cold Chromium packaging keeps
its complete target and cache policy. Other supported triples remain unmeasured.

### Qualified PCH producer inputs

Five existing Blink/V8 producers plus the generated V8 candidate can use their
pinned project headers as required inputs, retaining complete toolchain files.
Actual aquery removes 318,974 producer input edges, including 154,841 generated-file
edges. Blink producers fall from roughly 78k–80k inputs to 1.9k–2.4k. Arguments,
environment and execution requirements match exactly; no input paths are added.

A global attempt fails Content's parent-relative Skia include because file
closures alone do not preserve directory layout. Content keeps its full context.
The six qualified producers execute under Linux sandbox with raw PCH, validated
PCH and depfile bytes identical to their full-input baselines. Final qualification
of all seven producers passes. No include rewriting or directory fabrication.

This can improve readiness: normal C++ actions use include scanning, while the
custom producer treats declared headers as mandatory. Cold scheduling benefit
remains unmeasured. A separate strict-cold trial starts from d325eeb with only
five existing producer scopes changed; the compiler, six PCHs, complete archive
and cache policy remain unchanged. 215 tests pass for this combined candidate.

The complete V8 snapshot-generator binary also matches baseline bytes:
`965ee9de41d0843dd49080e11f644da51904c2629c892a3f0672dd1502f3b89c`.
This is warm sandbox correctness evidence only. The first local attempt exhausts
filesystem inodes; cleaning only completed own sandbox trash frees 201,557
entries. Retry uses a private 8 GiB sandbox and synchronous cleanup. Partial
supporting outputs are reused, so its phase timings are not a performance result.
Control: `/tmp/chromium-v8-generated-host-link-control-003/report.json`.

The combined candidate's cold verifier now requires seven PCH producers, seven
closure validators and one prefix guard. Missing or extra prefix checks reject
cold proof; 215 tests pass. The isolated six-PCH BB trial retains its original
verifier and remains separate.

### Content producer directory dependency

Content's relative Skia include needs native/content_forwarders to exist.
Its pinned project closure normalizes that path, so the earlier global
input-scope attempt omitted the directory. Declare one existing forwarder
header explicitly, as the other scanned source sets already do.

Actual sandboxed full/scoped runs preserve raw PCH, validated PCH and depfile
bytes against the frozen baseline. Both producer and validator execute uncached
under linux-sandbox in each variant. Aquery inputs fall 79,542 to 6,309, removing
73,233 edges, including 28,172 generated inputs. No new input paths; compiler
arguments, environment, execution requirements and complete toolchain files match.
Consumer declarations, compiler flags, source selection and link order are unchanged.

215 tests pass. This qualifies the input change; full strict-cold timing, archive,
ABI and rendering remain unproven. The current seven-PCH cold run predates it.

### Held Chromium-trained compiler and Content trial

The next prepared strict-cold candidate combines seven qualified project PCHs,
the explicit Content forwarder dependency and the existing Chromium-trained
compiler artifact. Archive c04cdca0eb8f94a93a2193200f5375356c7769cb53d3eb42ef75fd7ac95f0fa0
and driver 274f6c48c5de1dad64037c6239fb5310faf1d1844bd1f5bc56feef50b5ee85a4
are both pinned. Fetch uses the prior compiler-preparation CI artifact through
managed BuildBuddy auth, not a new release. Dependency fetch stays inside timing.

Its six-source BB comparison reduced compiler CPU 6.13% and wall time 9.23%
against D94. That narrow result does not establish full-build performance.
Chrome UI/Profile candidates and BOLT are excluded here. Complete target,
fresh state, seven producer/closure checks, one prefix guard and cache policy
remain unchanged. Only perf/strict-cold-c04-content-run triggers this candidate;
the ready branch is held while the existing seven-PCH run finishes.

Cold trials also stream `cold-resources.jsonl` beside the Bazel profile. Samples
contain cumulative cgroup CPU/throttling, memory/reclaim/OOM, pressure counters,
kernel CPU ticks and Bazel RSS. Compare counter deltas across elapsed timestamps;
old peak/OOM totals are not evidence that this trial hit those conditions.
Kernel and ancestor counters may include other workloads. Missing counters stay
unknown. Sampling changes no compiler flags, action inputs or cache settings.

### Strict-cold resource observation

BB invocation `e1ce7ada-5652-4c15-932c-6100c78c8613` at revision
`6d4d9664f20913df9902b2799c9e78e9dce96274` hit the tier timeout after
3602.232 seconds. Last observed progress was 78,932/102,669 actions; no archive.
The seven-PCH workload and C04 compiler were unchanged. Collector run
42518344105 preserves the incomplete profile and 710 resource samples.

Between elapsed 240.861 and 3557.095 seconds, cgroup CPU usage averaged 18.078
CPU equivalents. The late interval, 1800.020–3557.095 seconds, averaged 18.905
of 19 guest CPUs: 17.037 user, 1.829 system, 0.001 I/O wait and 0.028 steal.
CPU quota throttling counters did not increase. Guest/cgroup counters do not
independently establish physical allocation. These observations favor reducing
compiler work over another unchanged retry or increasing action concurrency.

Peak sampled Bazel RSS was 7,457,464,320 bytes. Pressure, memory.current,
memory.peak and memory.events were unavailable; absence of memory pressure is
unproven. Final file memory includes shared memory, so those values must not be
added. The trace is partial: its completed-action totals cannot establish final
work, remaining duration, archive identity, ABI or rendering. Other four triples
remain cold-unmeasured.

### Held ten-PCH cold candidate

The next held candidate combines the unchanged C04 compiler, seven qualified
PCHs and resource sampling with separate Chrome Browser.h, Profile.h and Content
public RenderFrameHost.h producers. The selected cohorts contain 312, 672 and
343 additional original consumers; known differing sources stay plain. Compiler
contexts, source coverage, alwayslink and object order remain unchanged.

The cold verifier requires exactly ten producers, ten closure validators and
one prefix guard. The complete Linux amd64 archive target, fresh state, no RBE
and no action/disk/remote/repository-contents caches remain unchanged. Only the
perf/strict-cold-ten-pch-run alias triggers this candidate. Hold that alias until
all 1,042 UI, 1,430 Profile and 1,161 Content objects, each archive, and the combined
9,350-object browser relink pass against frozen original outputs. Narrow local
ABBA results do not predict complete cold timing. Other four triples remain
cold-unmeasured. BOLT remains excluded pending full compiler/package validation.

Combined correctness gates pass: all 1,042 UI, 1,430 Profile and 1,161 Content
objects preserve frozen original bytes; each cohort archive matches. The full
ten-producer graph preserves browser/V8 link arguments, order and environment
after expected object-path substitutions. Relinking all 9,350 Chrome replacement
objects reproduces browser SHA-256
`21089926f88ecf518a8e5d53fa367df8b1ea76967c5b0b59491a83a9edf19294`.
218 tests pass. These are warm correctness gates, not cold timing or artifact
ABI/rendering proof. The separate V8 compiler pilot is excluded.

### Shared Base Bind.h experiment

A read-only survey finds 18,127 Bind.h consumers outside the 7,117 existing
project-PCH consumers. It covers 31,376 original native fastbuild C++ records;
all depfiles are present and parse without escaping exceptions. This is header
membership, not CPU attribution or a cold-duration forecast.

A 36-file pilot across twelve original owners reproduces every baseline object.
One producer cannot serve both member-pointer language modes: Clang rejects
33 cases. Two matching producer variants preserve all 144 object outputs across
four passes, retaining every consumer flag and normal Clang PCH validation.
Mean compiler CPU falls 83.408 to 66.488 seconds (20.29%), including both fresh
producers in each candidate pass. Four workers, warm inputs and shared local
hardware; no whole-build or BB timing claim.

An empty-source configuration probe accepts 1,558 of 1,559 contexts, covering
18,086 source records. The remaining 41 have a different optimization level and
stay plain. This probe does not qualify real source objects. Full source byte
qualification is complete. All 18,086 selected records match frozen original
objects after two verified temporary-output inode failures were retried. Both
original failure logs and matching no-PCH controls are retained.

Both manual producer declarations retain complete SDK inputs and validate the
same 112 project header paths. A separate Base context avoids a dependency cycle.
Default Base sources, dependency order, flags and link options stay unchanged.
Both producers and both closure validators execute under Linux sandbox, each
with 1,841 declared inputs. All 425 original Base compiler commands and effective
environments remain unchanged. The actual Bazel PCHs reproduce all 36 pilot
objects and accept the same 1,558 contexts. Their bytes differ from the prototype
PCHs; prototype full-corpus validation was retired after 8,054 matching objects.
The complete 18,086-source comparison uses the actual Bazel artifacts and passes
a separate reconciliation audit. All frozen object hashes and both PCH hashes
remain unchanged. Consumer rollout remains pending. The ten-PCH cold trial excludes this experiment; other
triples are unmeasured.

### Ten-PCH strict-cold result

Revision `92762b2190978ba33dae91ea534e551cf07de3e1`, invocation
`d1499426-618f-4e2b-a5d8-e64fc0c9c861`, reached the hosted one-hour limit at
3,600.546015 seconds without a completed archive. The under-one-hour goal remains
unmet; artifact ABI and rendering cannot be verified for this run. Fresh build
state, archive-only dependency reuse and disabled RBE/action caches were retained.
The collector succeeded in GitHub Actions run `42527193855`.

The 710 resource samples span elapsed 5.571–3,555.947 seconds. After elapsed
1,800 seconds, cgroup CPU usage averages 18.809 CPU equivalents: 16.607 user and
2.172 system. Guest I/O wait averages 0.014 CPUs and steal 0.030; quota throttling
does not increase. The observed guest exposes 19 CPUs and 35,262,926,848 bytes of
memory. Physical allocation and host page-cache state are not independently
controlled. Peak sampled Bazel RSS is 7,158,951,936 bytes; pressure and cgroup
memory peak/events remain unavailable. Shared memory is included in file memory.

The partial trace contains 19,092 completed CppCompile spans, 41,097.715 compiler
subprocess task-seconds and 2,798.672 sandbox task-seconds. These are overlapping
wall spans, not CPU measurements. Different scheduling and incomplete coverage
prevent throughput comparisons with earlier terminated runs. Late-stage CPU
saturation still favors reducing compiler work. Other four triples remain
cold-unmeasured.

### Opt-in shared Bind.h consumers

The manual Net cohort passes Linux sandbox checks: all 565 original objects and
archive SHA-256 `e114a6ce71addda9f03a37454533bd1d05250ef5f9a02e7fd602a68669cb2d44`
match, including 323 Bind.h consumers and 242 plain sources. Both original .cpp
sources retain their compiler flags and object bytes. All default Net actions
remain unchanged; importer compiler flags and effective environments match the
frozen execution inventory. The two Base PCH artifacts remain unchanged. This
is warm correctness evidence, not timing or a cold archive result.

`CHROMIUM_BASE_BIND_PCH=1` opts Net into that cohort and adds disjoint Bind.h
groups to the existing UI, Profile and Content PCH rules. These add 705, 641 and
444 consumers. Combined sandbox, global compiler-context and full browser-link
checks are pending; the flag remains off by default. The reachable graph should
contain eleven producers: ten existing producers plus the shared default-mode
Base producer. The complete-member-pointer producer remains manual until a
matching consumer is qualified and routed. Other four triples are unmeasured.

This candidate also carries the separately qualified shared V8 compiler cohort
from `8da2a44`. Its 188 objects and archive, all 9,538 global compiler contexts,
and complete browser/mksnapshot relinks match their frozen references. It reuses
the existing Isolate PCH, adds no producer, and keeps eleven compiler sources
plain. Shared-cohort BB/cold performance and complete artifact ABI/rendering
remain unverified.

### Broad Bind.h routing

A separate opt-in wrapper prepares 17,894 compatible Bind.h records across 2,616
owners in 22 native declaration families. The membership file excludes the 41
optimization-mode mismatches and 192 manual/binary-owner records. It includes
both existing member-pointer language modes. The full archive graph routes
17,881 records; thirteen unsupported records retain their original rules.

The wrapper retains each original cc_library by default. With the explicit
Base Bind flag, supported C++ owners use a separate compilation context and
ordered archive cohort; the original rule retains its headers, dependencies
and link options. Existing UI/Profile/Content partitions retain their disjoint
PCH groups. Mixed-language sources, selectors, duplicate object names, private
implementation dependencies and nocopts remain on their original rules.

Full native source-byte qualification passes against the actual Bazel PCH
artifacts: 18,084 direct matches plus two matching infrastructure retries.
All 18,086 original reference hashes are unchanged; 41 incompatible records
stay plain. All 52,516 unique compiler/header-check contexts preserve their flags,
include order, defines and environment. All 6,780 unique link/archive commands
preserve flags and ordering after cohort path substitutions. Actual Bazel builds
also reproduce all 425 original Base objects. These are local correctness checks;
other four triples remain cold-unmeasured.

The three newer UI/Profile/public-RFH producers also prepare narrower declared
inputs: pinned project header closures plus the complete SDK. The public RFH
producer retains its forwarder directory anchor. Producer commands, effective
environments and raw/validated PCH and depfile bytes match their full-context
predecessors in fresh sandbox executions. Inputs fall from 108,433 to 2,833 for
UI, 108,504 to 2,003 for Profile, and 79,542 to 2,179 for public RFH. Each retains
all 1,729 SDK inputs. No isolated cold speedup is claimed.

An independent original V8 depfile survey finds 199 remaining Isolate.h records
across native and host configurations, including previously known exceptions.
Most are generated class definitions: the base library depends on that owner,
so directly reusing its Isolate PCH there would introduce a dependency cycle.
The remaining builtin-generator candidates need their own context and byte
qualification. No additional V8 source is routed from this survey.

### Broad Bind.h cold result

The separate cold-run preparation accepts `--base-bind-pch` only with the existing
project/Blink/native Linux configuration. Its proof requires the effective
`CHROMIUM_BASE_BIND_PCH=1` canonical BEP option, exactly twelve executed producers,
twelve closure validators and the existing prefix guard. Missing flags, stale
ten-producer results, missing validators and extra producers fail verification.
Cache, sandbox, resource and elapsed-time policy remain unchanged.

The twelve-PCH candidate `4ea795f` ran in BuildBuddy invocation
`ce4581b8-1d1e-4598-a54e-d66fff155837`. It hit the one-hour tier limit at
3,601.903 seconds without an archive. The partial trace contains twelve completed
producers and twelve closure validators. The under-one-hour goal remains unmet;
other four triples remain cold-unmeasured. Plugin dependency pruning below was
excluded from this run.

Same-run resource samples show 18.866 CPU equivalents during seconds 2,401–3,497
on the observed 19-CPU guest, with zero cgroup throttling and about 0.0014 CPU
equivalents of kernel I/O wait. These counters describe the guest/cgroup, not
individual compiler CPU. Early seconds 301–1,200 average 15.432 CPU equivalents.
The late bottleneck is CPU work; the trace does not establish a full-build
completion estimate.

All twelve closure validators finish in the partial trace. String and Base Bind
are ready by 567.4 seconds, public RenderFrameHost by 686.8, Document by 1,014.3,
and the two V8 producers by 2,733.0. Wider reuse must preserve compiler context,
object bytes and dependency acyclicity. Counts from unfinished traces do not
prove throughput improvements over previous trials.

The terminated ten-PCH trial's captured trace contains completed actions for
seven producers and their validators; it contains no completion for the newer
UI/Profile/public-RFH producers. The trace ends before outer termination, so
this does not prove those producers never started. Narrower inputs target their
availability; improvement requires a new measured cold result.

### Compiler plugin dependencies

The partial ten-PCH trace records 861 Protobuf compilations and 2,508.274
CppCompile task-seconds across several configurations. Task time is not CPU
time. Required bounds/RTTI settings differ, so collapsing configurations or
using a prebuilt compiler without matching those settings is not justified.

The change narrows only plugin library dependencies. The JavaScript
plugin uses the public code_generator API; proto_extras also needs importer and
C++ names. Perfetto plugins use a bounds/RTTI-configured code_generator/importer
library. The full public protoc_lib target and actual protoc compiler remain
available. The importer records the same consumer-specific mappings.

Compiler mode, hardening and tool version stay pinned. The full archive graph
removes 204 object compilation actions and adds none. All retained contexts match
except unused include paths in seven plugin compilation contexts.

Real sandbox builds compile and link all five plugins, then execute 159 existing
generation actions across target and execution configurations. All 1,556 generated
files and all seven plugin objects match baseline bytes. Plugin executables
relink with different layouts. These are warm correctness checks, not cold timing.

### Wider existing PCH reuse pilot

A warm raw-compiler ABBA pilot compares current compilation against wider reuse
of three existing PCHs, with twelve sources per header. All 144 object checks
match frozen originals. Mean compiler CPU falls 19.6% for public RenderFrameHost,
14.2% for Document and 5.4% for String. Existing PCHs are reused, so these totals
exclude producer and sandbox costs; they are not a cold-build forecast. The
last baseline phase overlaps a read-only Bazel dependency query.

A configured graph query excludes owners already reachable from each producer,
including their existing compilation-context/cohort variants. After this
conservative cycle check and source deduplication, 3,502 candidates remain:
2,234 public RenderFrameHost, 395 Document and 873 String. These counts describe
qualification candidates, not adopted routing or proven speedups. Full source
byte qualification, integration/context/link checks and cold timing remain
required. Existing larger Browser/Profile/private-RenderFrameHost/IDL PCH
consumers keep their current producers.

### Generator input directory setup

Staging creates each input parent directory once per action. Each action still
starts with a private temporary directory; copying, metadata and logical paths
stay unchanged. A pinned Python 3.11 ABBA replay of twelve real WebUI/TypeScript/
GRIT actions preserves all 69 output files across 48 executions. Mean child CPU
falls from 15.294 to 14.584 seconds, a 4.64% reduction in this sample. The local
header-preparation build remained active, so wall time was uncontrolled. This
is warm supporting evidence, not a complete cold-build speedup.

### Reuse the execution-configured Protoc

Protoc opts out of native target sharing and uses the BCR execution compiler
already needed by Quiche. This replaces its extra target fastbuild configuration
with the existing optimized execution configuration. Protobuf 33.4 and the
bounds-checking/RTTI definitions stay pinned; other native tools keep their
existing sharing policy. Both importers preserve this choice on regeneration.

Real Linux sandbox builds execute all 423 selected generators: 422 Python actions
and one genrule, including downstream asset generators carrying the tool input.
All 4,028 generated outputs match original bytes. The resulting tool binary
matches the original execution compiler. The full archive graph removes 187
compile, 69 link and 68 archive action views, adds none, and preserves every
retained command/environment, including all twelve PCH producers. Removed views
belong only to the original Protoc dependency closure. Counts describe registered
actions, not executed cold work.

These are warm correctness checks, not a timing comparison: the original phase
also built missing tools. All 219 tests pass. Full cold timing and final artifact
validation remain required; the other four triples remain cold-unmeasured.

### Remaining-work audit

The current native inventory contains 38,848 distinct source/compiler-command
views after normalizing only output, depfile and random-seed paths. No exact
cross-owner duplicates remain. This does not establish equivalence between
contexts with different flags or headers; no object-sharing change is adopted.

All 72 surveyed stdlib sources have identical normalized flags/environments
across eight registered views each. The old partial BB trace matches 237 spans
and 214.704 task-seconds for these contexts. This is partial diagnostic coverage,
not CPU savings or a cold-build forecast; complete input/ABI proof is missing.
Broader reuse of existing PCHs remains the higher-priority experiment.


### Strict-cold run after plugin and staging changes

[Run c6bf993](https://formatjs.buildbuddy.io/invocation/83786630-fec6-42dc-9c34-8508c2b19bee)
hit the free-tier timeout after 3,600.81 seconds. No archive completed. The runner
reported 19 CPUs and 35,262,926,848 bytes of RAM despite the 16-CPU/32GB request.
The recovered incomplete trace contains 20,024 completed C++ spans and 709
resource samples. Late samples average 18.89 CPU equivalents, with no quota
throttling. More parallel jobs would not address that CPU work.

Against the preceding incomplete run, 260 matched complete native cohorts have
a task-time ratio of 1.0043; 7,600 matched generator groups have a ratio of
0.9296. These are task durations across different runs, not isolated CPU
measurements or a full-build speedup. All twelve PCH validators finish by trace
second 1,499; earlier readiness alone has not delivered a complete build.

The next two attempts failed before compilation on GitHub HTTP 504 responses.
An official, checksum-verified Skylib mirror now precedes upstream fallback.
A separate [LLVM transport diagnostic](https://formatjs.buildbuddy.io/invocation/182d297f-1df3-4e9b-98d0-80acc73f3da2)
then fetched the exact pinned 182,710,697-byte source archive through both
Python (6.48 seconds) and Bazel (10.08 seconds). This proves transport recovery
at that observation, not build performance. The subsequent strict-cold retry
includes qualified Protoc reuse and retains the same compiler/cache policy.

Wider PCH qualification now holds Bazel's output-base lock during raw compiler
work. An actual concurrent Bazel invocation exits with lock error 9. A public
`CcInfo` object selector also rebuilt one original object through a real Linux
sandbox and matched its raw reference bytes. Neither check qualifies wider
routing; full source, configured graph, sandbox, link and archive proof remain.

### Declared npm tree experiment

Package closures become declared Bazel tree outputs, copied once with pinned
Python. Generators link immutable package contents. Explicit file aliases get
private copies with their original permissions; conflicting contents fail.
Node preserves logical symlink paths, keeping Chromium's dependency guard intact.
Each cold invocation builds its own tree; no cross-build cache is introduced.

An initial raw ABBA replay of twelve real generators preserves all 69 output
files across 48 executions. Child CPU falls from 26.435 to 17.654 seconds
(33.2% in this sample), excluding tree setup and sandbox costs. This predates the
permission-preserving alias merge and is not a production or cold-build forecast.

The actual tree action runs in a Linux sandbox and matches all 3,935 original
file hashes. The final wrapper also passes twelve real generator roots in Linux
sandboxes, preserving all 69 original output hashes and the tree contents.
All 222 tests pass, including permission and input-immutability regressions.
The full Linux sandbox proof covers all 2,440 actions whose actual inputs carry
npm packages: 18,072 outputs match original hashes. The remaining 24 outputs
already vary in 50 unchanged-original replays: 23 Rollup configs embed the
private staging root, and DevTools workspace JSON derives its UUID from that
root. Comparisons preserve every other byte in each config and every other JSON
field; each UUID must equal UUIDv5 of its exact root and pinned namespace.
These files are not claimed byte-identical or reproducible.

Rollup resolves module symlinks independently of Node. Its standard
`--preserveSymlinks` option keeps source-map and request-list paths logical;
both maps and both request lists now match original bytes. The patch applies
to all five Chromium source projections. Package contents remain immutable.

The final wrapper's separate 48-execution ABBA replay preserves all 69 original
outputs, including explicit alias permissions and immutable tree contents.
Child CPU totals fall from 26.834 to 18.572 seconds (30.8% less).
PCH qualification runs concurrently; these warm task-CPU samples exclude tree
setup and sandbox costs. They do not forecast full cold timing. Strict-cold
archive timing and artifact validation remain required. Other four target
triples remain cold-unmeasured.

### Qualified wider PCH routing

A persistent rerun supersedes the lost raw pilot. Routing reuses existing
public RenderFrameHost, String and Document PCHs for 3,455 sources across 524
owners: 2,210 RFH, 859 String and 386 Document. Existing larger PCH cohorts stay
intact. Sources with changed object bytes or no measured single-pass CPU gain
remain outside this routing.

The complete configured archive graph retains all 52,312 compile, 854 link,
5,784 archive and twelve producer commands/environments after only explicit PCH
imports and expected object/depfile/random-seed path substitutions. Archive
member ordering stays unchanged. Real Linux sandboxes then execute all 3,455
routed compiles; every object matches its frozen original reference. All twelve
PCH producer artifacts remain byte-identical. Producer extras now propagate to
importers, preserving directory anchors in Clang's recorded header paths.
Validation and complete SDK inputs remain enabled.

A separate stratified 36-source ABBA sample executes 144 compiles with identical
objects. Compiler CPU falls 12.8% for public RFH, 16.1% for String and 13.7% for
Document. These warm samples exclude sandbox/producer costs and do not forecast
cold timing. Full strict-cold archive completion, ABI and rendering validation
remain required; other four triples remain cold-unmeasured.

### Strict-cold result after npm and wider PCH reuse

[693db8c](https://formatjs.buildbuddy.io/invocation/edbca27b-a0d6-4fdd-b279-584b33c85291)
timed out after 3,603.32 seconds without an archive. The 19-CPU runner sustains
18.90 CPU equivalents late in the run, with no quota throttling and negligible
I/O wait. Against b31c0bb, 7,608 matching generator groups take 0.7311 times
the task duration; 235 complete native control cohorts take 1.0603 times.
Both traces are incomplete. Task durations include scheduling and host variation;
neither comparison proves a complete cold speedup.

Nine deterministic V8 samples run with Clang time tracing preserve original
object bytes. Frontend work accounts for 82.2% of their traced compiler time;
generated samples repeat about two seconds of pending template instantiation.
Standard PCH code emission with companion objects shows no CPU gain and stays
rejected. Eager template instantiation is a separate candidate: it precomputes
template bodies while retaining normal object emission and content validation.

The candidate keeps original PCHs and routes only explicitly qualified sources
to separately validated eager variants. Mixed routing executes nine real sandbox
compiles with identical objects, including one original fallback. All 1,014
registered compile commands and three archive commands retain flags, environments
and object paths, except eight expected PCH operands. Original archive member
order stays intact. Raw qualification then compares all 5,183 available source consumers across six
families: 4,716 objects match originals, 467 changed candidates stay on original
PCHs, and every original control succeeds. The manifest contains only matching
sources. Routing is enabled only with the measured Base Bind configuration in
fastbuild mode; other configurations retain original imports.

A separate 72-source stratified ABBA replay preserves all 288 object hashes.
Compiler CPU falls 6.7% for Document, 3.7% for String, 4.6% for module IDL,
53.3% for generated V8, 7.7% for V8 isolate, and 45.0% for private RFH.
Both paired comparisons improve in every family. The smaller String/IDL gains
save 81.7/167.9 CPU-seconds in their full raw identical-source replays; their
complete extra eager producers cost 1.35/1.56 CPU-seconds. These are warm CPU
measurements, excluding sandbox/setup costs, not cold timing forecasts.

Cold verification requires every named eager output, matching raw/validated PCH
bytes, allowed producer names and execution counts matching produced pairs.
Unused original variants may be pruned; an isolated Bazel provider test confirms
that behavior. Missing eager outputs, missing or changed validation copies,
unexpected producers and inconsistent counts fail verification. Cache policy,
fresh roots and actual sandbox requirements stay unchanged.

Full configured-graph audit preserves all 52,312 compile commands, 854 link
commands and 5,784 archive commands, including environments and archive member
ordering, except the 4,716 qualified PCH imports and six extra eager producers.
Final mixed routing executes all 4,716 selected objects in actual Linux
sandboxes; every object matches its original hash. All 12 original PCH hashes
remain unchanged, and all six eager PCH hashes match raw qualification. Fixture
cleanup and frozen input checks pass. This warm correctness run uses cached
prerequisites; it makes no cold timing claim. Complete strict-cold archive, ABI
and rendering validation remain pending. Other four triples remain
cold-unmeasured.

### Serialization prefix qualification

The eager-template revision `da01479` still hits the BB one-hour limit at
3,601.20 seconds without an archive. Its incomplete trace contains 20,202
completed C++ compile spans, versus 19,605 previously. The complete 248-source
generated V8 cohort takes 0.5131 times its previous task duration; 244 unchanged
native control cohorts take 0.9951 times. Task durations include scheduling and
host variation. These partial traces do not establish total cold speedup.

A Base/Mojo serialization prefix uses only existing public header dependencies,
the complete SDK and standard eager template instantiation. Raw qualification
checks all 8,263 naturally including consumers against their original sandbox
objects: 8,142 match, 121 stay on their original PCH, and no original compile
fails. Full raw/sandbox qualification uses D94, the earlier compiler built from
the same pinned LLVM source. The manifest names matching sources explicitly.
Other configurations keep their original imports.

The exact pinned BB compiler reproduces both baseline and serialization PCH
bytes. A separate 24-source ABBA replay keeps all 96 object hashes unchanged and
uses 0.9225 times the baseline compiler CPU. This is a warm sample, excluding
producer and sandbox costs.

Configured-graph audit preserves 52,312 compile, 854 link and 5,784 archive
commands, environments, object paths and archive member order after only the
qualified imports and additional producer are normalized. All 19 PCH producers
retain the original complete 1,729-file SDK input set; the original twelve
producers retain their entire input sets. Actual Linux sandboxes then execute
all 8,142 routed objects; every hash matches its frozen original. All twelve
original PCH hashes stay unchanged, and the serialization PCH matches raw
qualification. The run executes 12,683 C++ actions including prerequisites;
only Linux sandbox and internal runners appear. Frozen-file and fixture cleanup
checks pass. This warm correctness run reuses prerequisite outputs and makes no
cold timing claim. Complete cold archive, ABI and rendering validation remain
pending; other four triples remain cold-unmeasured.

Cold resource samples also record cumulative Bazel process CPU and reaped child
CPU when `/proc` counters are available. Compare deltas; running children are
not yet included in child totals. This separates Java overhead from compiler
work without changing compiler commands or cache policy.

The complete devbox baseline exposed a verifier bug: Bazel 9.2 reports only the
20 busiest action mnemonics by default. PCH producers and validators fell below
that cutoff, so a successful archive with matching PCH files failed the action
count check. Cold runs now request all mnemonic metrics. Existing reports stay
unchanged; any retrospective proof must use the retained execution log.

The completed devbox baseline at `da01479` took 6,955.77 seconds including archive
copy (6,954.71 seconds inside the cold harness). Actual quota: 16 CPUs / 48 GiB,
Xeon Platinum 8488C; exact C04 compiler. Fresh output/install/user/tool state,
dependency archives only reused, RBE and action caches disabled, OS page cache
uncontrolled. Local caches within one run are permitted for future experiments;
no derived cache state may cross cold-run boundaries.

BEP records 104,735 actions, including 48,768 C++ compiles. Independent decoding
of the retained compact log verifies 58,754 Linux sandbox spawns, zero failed
spawns/cache hits, all 17 PCH producers/validators and one prefix action. Raw and
validated PCH output digests match. This supplements the original failed verifier
report; it does not rewrite that report. Exact archive SHA-256:
`85f60957ad372185d1b05606f8ffd033315fb984875f3f7b6bc1b7ba1aad39c8`.
GNU ABI, relocated browser, JS/CSS/Intl/layout and both screenshot scenes pass;
both scenes have zero changed pixels.

Among 250 native cohorts complete in both traces (2,957 sources), devbox task
wall time is 0.6187 times the timed-out BB run. This is a limited cohort comparison,
not a completed BB total or isolated hardware speedup. C++ BEP user + system CPU
is 81,653.40 seconds: 85.06 minutes at 16 CPUs before other work. Saving wrapper
overhead alone cannot meet the hour target.

Next V8 prototype adds `objects-inl.h` to the current eager isolate prefix. All
553 current eager baseline objects reproduce with exact C04 compiler. Normal
expanded imports preserve 424 objects; eager imports preserve 289 of those. The
other 129 retain their existing route. Both compiler builds reproduce all three
canonical sandbox PCH artifacts. Paired ABBA on 32 source-byte quantiles, 16 per
owner, preserves all 128 objects and uses 180.24 versus 324.67 compiler CPU seconds
(0.5551 ratio). This remains a warm prototype: production mixed routing, full
SDK/global graph checks and a new cold archive remain required. No overall cold
speedup claimed. Linux amd64 still exceeds one hour; BB goal remains unmet and
the other four triples remain strict-cold unmeasured.

Expanded V8 imports are now integrated behind the existing fastbuild/native Linux
PCH opt-in: 289 eager, 135 normal, 129 retain the prior eager isolate import. Two
explicit producers share the same qualified prefix and public C++ context. Cold
verification requires both additional producers when their source sets are used.

The mixed-route correctness run selects exact C04 compiler through the LLVM root
index API, then restores the original index/compiler. All 424 selected objects
execute in Linux sandboxes and match original bytes; both new raw/validated PCHs
match the qualified artifacts and the 12 original PCH byte hashes remain equal.
The run executes 2,794 C++ compiles including prerequisites, with only sandbox
and internal runners. All 21 producer SDK path sets contain the same 1,729 files;
the original 12 complete producer input sets are unchanged. Full registered graph
checks preserve 52,312 C++ compile commands, 854 link commands, 5,784 archive
commands and archive member order after only qualified import normalization.
226 Python tests and formatting pass. This is warm correctness evidence, not a
new cold archive or overall speedup result. BB under-hour remains unproven.

The complete `ec52236-003` devbox run finished on 2026-11-09: 6,638.58 seconds
including archive copy, 6,637.51 seconds inside the harness. Same 16-CPU / 48-GiB
machine, exact C04 compiler and cache policy as the baseline. Cold verification
passes, with zero cached actions, 104,744 BEP actions and 48,768 C++ compiles.
One run per revision: elapsed time decreased 4.6%; this is not a confidence interval
or an isolated estimate of each optimization. The complete trace is retained.
Archive SHA-256:
`a671344aaa7ead39e554a4472c9020d2ec5d87cc36dc83107504e433355b018e`.

The browser binary is byte-identical to the passing baseline, SHA-256
`21089926f88ecf518a8e5d53fa367df8b1ea76967c5b0b59491a83a9edf19294`.
Relocated native JS/CSS/Unicode/Intl/layout smoke and Qt 5.15.2 / 6.4.2 GNU ABI
checks pass. Initial layout screenshot failed: 1,512 changed pixels, 0.5833%
versus the unchanged 0.5% threshold. Its bottom region contains duplicated page
content. Three alternating replays per baseline/new binary all pass, both scenes
with zero changed pixels. Preserve the original failure; capture instability is
unresolved. No baseline, tolerance or browser flags were changed for these replays.

Under one hour remains unproven. Current C++ user + system CPU is 78,202.30 seconds:
81.46 minutes at 16 CPUs, excluding all other work. Reaching 3,600 seconds requires
46% less elapsed time. Small PCH gains and scheduling changes cannot close that gap.

Next experiment is explicit Clang header modules, starting with consistent SDK
ownership and one real Chromium source. Gate adoption on original object bytes,
complete declared SDK inputs, normal validation, cross-sandbox imports and
reproducible outputs. A representative slice must include module production,
Bazel/sandbox costs and enough source owners to expose context fragmentation.
Require throughput near twice the current build before spending another full
cold run on this route. SDK bootstrap alone is not Chromium compatibility or
performance evidence. If that gate fails, no demonstrated under-hour route exists
on this hardware; keep the target and report the gap honestly. Other four triples
remain strict-cold unmeasured.

Feasibility budget after the completed run: leaf cgroup CPU increased by
104,030.80 seconds, averaging 15.67 of 16 CPUs. Last sampled Bazel process CPU
is 19,265.98 seconds; C++ BEP CPU is 78,202.30 seconds. The remaining 6,562.53
seconds include generators, sandbox processes and unmeasured process tails.
Bazel's last process sample precedes exit; same-container unrelated work could
also affect cgroup totals. These are attribution estimates, not disjoint sampled
stacks. High CPU utilization leaves little scheduling-only opportunity.

Holding other CPU work and observed efficiency constant gives this optimistic
sensitivity model; new producer costs and context fragmentation are excluded:

| Hypothetical change | Estimated minutes |
| --- | ---: |
| C++ 1.5x faster | 82.9 |
| C++ 2x faster | 69.1 |
| C++ 2.5x faster | 60.7 |
| C++ 2.7x faster | 58.3 |
| C++ 2x and Bazel 2x faster | 58.8 |

The earlier near-2x compiler gate is insufficient by itself. Before another full
cold run, require a weighted CPU budget covering compiler, Bazel, generation and
new producer costs that predicts at most 50–55 minutes, leaving margin for graph
tails and variance. First measure frontend share across a CPU-weighted source
sample, not only the eight deliberately selected hot sources. Use that share to
bound possible gains before expanding module infrastructure. Separately profile
Bazel's roughly three-core average CPU usage; reducing half is a hypothesis,
not a demonstrated optimization. No new experiments started after the user pause.

Pure proportional hardware scaling estimates 73.8 minutes at 24 equivalent CPUs,
55.3 at 32 and 36.9 at 48. These are optimistic arithmetic bounds, not measured
predictions: serial work, memory bandwidth/capacity and CPU model affect scaling.
A 32-CPU machine has little margin for one hour; 48 provides more room if a future
hardware change is authorized. The current goal still names the existing devbox.

The final bounded module probe completed during pause cleanup: consistent explicit
SDK dependencies plus a Base Bind module compile a real
`render_process_host_impl.cc` object byte-identically with exact C04 and all 1,729
SDK inputs. Fixture and original compiler were restored. This establishes only
one-source compatibility, not population coverage, reproducibility or speed.

Executed-work audit of `ec52236-003` decodes all 48,768 C++ compile spawns from
its compact execution log, matching the invocation ID. They cover 46,168 distinct
source paths. 1,522 paths appear more than once, accounting for 2,600 additional
compiles (5.3% of compile actions). Identical command/environment/input-set-ID
replays: zero. After normalizing output, depfile and random-seed paths, only two
matching command pairs remain: NSS `empty.c`, about 0.023 aggregate task-seconds
beyond one compile per pair. Their input-set IDs differ, so even these are not
fully proven equivalent actions.

Configuration-path normalization exposes a concrete remaining candidate:
libc++ `locale.cpp` executes in five configurations with matching flags after
configuration paths and output seeds are normalized. Header/input digests and ABI
still need comparison before sharing. The expensive inspected Protobuf repeats
include distinct bounds-checking/RTTI defines; SQLite also has differing build
flags. Sharing these blindly would change behavior. Output-path normalization
alone cannot prove configurations interchangeable.

All repeated-source groups together contain 1,288.36 aggregate subprocess
wall-seconds beyond their cheapest compile per source. This is neither CPU nor
elapsed savings; removing variants can also affect prerequisite and Bazel costs.
The evidence supports targeted stdlib/configuration cleanup, not a claim that
Chromium is being compiled twice or that duplicate-source cleanup closes the
under-hour gap. No new builds were run for this audit.

The current user target is now 90 minutes (5,400 seconds), with the same complete
archive, cache policy and hermeticity requirements. The 6,638.58-second result
needs 18.7% less elapsed time. The local harness accepts `--target-seconds 5400`;
its cancellation limit follows that target unless explicitly overridden.
`--max-seconds 0` still permits an overrun to finish. Reports retain the literal
`under_one_hour` fact and add `target_seconds` / `under_target`; success still
requires the complete cold-policy proof. Final acceptance also checks the outer
launcher duration and exact archive ABI/rendering. 227 Python tests pass,
including a 4,000-second verified build accepted only under the longer target,
the strict 5,400-second boundary and rejection of cached or invalid runs.

A 128-source systematic PPS diagnostic samples the native inventory matching
81.8% of complete cold compiler task wall time. Every traced object matches its
independent native control with exact C04. Replay-CPU-adjusted frontend fraction
is 91.6%. Weights approximate CPU using prior task wall; tracing overhead and
another CPU model limit precision. Detailed Source/template spans overlap.

The explicit Base Bind/SDK module pilot preserves the real Content object's
bytes and full SDK but uses 45.83 versus 44.75 compiler CPU seconds in ABBA
(two compiles per variant). That one-source pilot offers no demonstrated win.
A separate 56-source broad serialization/tracing/Abseil/Protobuf prefix preserves
51 normal and 41 eager contexts. Compatible subsets use 0.8977 and 0.8300 times
baseline compiler CPU. Unchanged rejected/untested contexts reduce the weighted
whole-compiler estimate to roughly 3–6%, before producer/graph costs; this alone
cannot reach 90 minutes. Normal/eager closures each contain 416 project headers.

Bazel's supported command CPU profiler captures stacks on the 128-source warm
diagnostic. Nested-set flattening, hashing and sandbox symlink creation/deletion
appear prominently. This includes cached graph checks and is not a complete cold
CPU attribution. Sandbox reuse preserves all 128 native object hashes. Warm build
wall falls 104.13 to 93.88 seconds, while Bazel CPU rises 674.70 to 683.65 seconds;
this pair does not establish cold CPU savings. Fresh private RAM mounts keep reuse
within each run. Neither modules nor sandbox reuse is adopted as an optimization.

The next bounded pilot retains each sampled context's original prefix, adding
measured shared roots and SDK headers. V8's tracing registry conflicts with Base's;
V8 therefore keeps its original context and extends only SDK headers. All new
project closures must be discovered with declared inputs, pinned, then validated
before source timing. Complete population, graph and cold qualification remain
required before rollout.

The expanded 128-source pilot now preserves 110 normal and 92 eager contexts.
All 32 full-input PCH/depfile pairs match their frozen-closure versions exactly.
Fixed compatibility priority (eager, normal, original) models 17.5% less whole
C++ CPU, or about 96.1 minutes before new producer and graph costs. This remains
a training-sample estimate, not a cold result.

An early prefix forced `field_trial_params.h` into previously unrelated sources.
Its explicit `FeatureParam` instantiations added weak constructors, including to
otherwise empty generated objects. Those byte changes are rejected. Prefixes now
add that dependency only where the original closure already owned it; no symbol
stripping or compiler validation bypass is used.

SDK-only prefixes built with each original source's exact context preserve all
25 sampled plain-source objects. Normal/eager compiler CPU ratios are 0.8907 and
0.8834. Combining this fallback with the expanded prefix by fixed compatibility
priority preserves 125/128 contexts and models 19.8% less whole C++ CPU, about
94.1 minutes. The SDK trial uses 50 per-source producers, so it is an upper bound
until shared producer families and their costs are qualified. No production
routing uses these experimental prefixes. A separate, disjoint 128-source
holdout is selected but has not run.

One Parallel GC diagnostic preserves all 128 native object controls. Bazel CPU
falls from 674.70 to 643.48 seconds (4.6%); build wall falls from 104.19 to 96.97
seconds. Compiler CPU rises 1.3%. Both include analysis and cached graph checks;
neither establishes complete cold-build savings. Runtime tuning needs replicated
measurements before adoption. Current work targets deeper component prefixes,
shared SDK contexts and independent holdout validation before another cold run.

Two component pilots extend existing Blink, Chrome UI/Profile, Content and V8
prefixes with headers identified by the frontend traces. Across 45 training
contexts, 35 normal and 26 eager imports preserve native object bytes. Each
pilot's full-input PCHs and depfiles match their scoped counterparts. The first
30-context pilot's compatible eager subset uses 0.3877 times baseline compiler
CPU; the remaining 15-context pilot uses 0.2995 times baseline on its compatible
eager subset. Rejected imports retain their earlier route.

The SDK prefix now shares eight representative contexts across all 25 sampled
plain sources: 16 producers instead of 50. Normal/eager CPU ratios are 0.8813
and 0.8777, with all object bytes preserved. Seven initial families rejected two
imports because `SK_USER_CONFIG_HEADER` values differed. Grouping also checks
overlapping command macros; no compiler or consumer flags are overridden.
All 16 dependency files contain only the generated prefix and declared SDK
files/tree children. Every consumer retains the same 1,729 SDK inputs.

The frozen priority is component eager, component normal, global eager, global
normal, shared SDK eager, shared SDK normal, original. Across the 128 training
contexts, 125 import a byte-compatible prefix. The whole-C++ point estimate is
28.0% less CPU. Counting 383.37 measured CPU seconds for all 70 additional
producers gives about 87.7 minutes at the completed cold run's CPU utilization.
New graph/validator costs and sampling uncertainty remain; this is not a cold
build result. The disjoint 128-source holdout now has queued global, component
and SDK trials, using frozen families and priority. Unsupported SDK contexts
keep original/global routing. No production routing has changed.

The disjoint holdout is complete. Global normal/eager imports preserve 106/80
of 128 contexts; component prefixes preserve 32/19 of 44. All 28 supported SDK
contexts preserve bytes in both modes; four unmatched plain contexts retain
their original/global route. Frozen priority imports 122/128 contexts and models
26.0% less whole C++ CPU: 89.43 minutes including producer CPU, before new graph
and validator costs. Training/holdout average is 88.57 minutes; two systematic
offsets do not establish a confidence interval. Margin remains thin.

Raw holdout collectors rejected an environment comparison: execution logs include
sandbox-injected `PWD=/proc/self/cwd`, while public action metadata omits it.
Original failures remain preserved. Recovery checks every argument and effective
environment, then verifies all 128 native controls and 256 probe baseline objects
against SHA256 digests from the actual completed cold build. Accepted imports
must match those same digests. Probe children omit injected `PWD`; relative CPU
estimates retain that limitation. Production native execution is unchanged.
All 48,768 cold object digests are indexed as correctness references. Reusing
them for qualification requires command/environment and input provenance checks;
the final cold benchmark still starts with fresh build state.

`chromium_pch_compile` now accepts optional `object_suffixes` so replacement
prefix groups can retain existing object paths and archive order. An actual C04
Bazel integration test compares canonical and aliased groups: compiler flags,
paths, object bytes and archive bytes match. Default suffixes, explicit empty
suffixes and invalid group rejection are checked. No routing tables are enabled
by this interface change. All 227 Python tests pass.

A reference-free qualification probe removes its original object temporarily,
then builds only a public shadowed compile. One sandboxed candidate executes,
zero original `CppCompile` actions execute, and its object matches the actual cold
digest with all 1,729 SDK inputs retained. The original object, fixture and
compiler selection are restored. This supports avoiding duplicate baseline work
during qualification; full-population input provenance still needs verification.

Actual shared-prefix declarations preserve 247/256 training and holdout contexts
under frozen priority. All 70 full-input/scoped PCH and dependency-file pairs
match. SDK contexts use captured effective macros without GN library dependencies,
so lower libraries can import them without dependency cycles. All 57 affected
plain contexts retain their earlier decisions after this change. Candidates remain
manual; production source routing is not enabled.

Cold input auditing covers 157,758 logical files. It exposed two generator leaks:
gperf recorded executable paths in comments; SPIRV-Tools eagerly queried ambient
Git even when its version description was forced. gperf now uses an explicit stable
invocation name through staged tools. Other tools retain directory and multicall
lookup. SPIRV-Tools uses declared `BCR-2026.1` metadata and never queries Git when
forced. Regression tests exercise real pinned tools across different paths and
fake parent Git descriptions. These fixes change generated provenance, not compiler
options. Four freshly executed gperf native objects match completed cold digests after
the invocation-name fix. All 228 Python tests pass; the real Bazel generator
regression passes all three cases. Full population qualification still gates every
replacement against its actual cold digest and command/environment signature.

Raw-library replacement now supports duplicate basenames through explicit numbered
object order. Wrappers can hide the private compile context while retaining their
original public headers and defines. A real C04 integration uses two `same.cc`
files and an implementation dependency: object bytes, archive bytes/member order,
public context and linked executable bytes all match the ordinary library.
Reusing the ordinary owner's compile name collided with its module-map action,
so that approach was dropped. Replacement keeps its own Bazel output/seed paths;
these three objects remain byte-identical. Full-population routing still needs
producer dependency checks and final native object validation.

The routing planner also checks cycles introduced by combinations of imports,
not only direct producer ancestry. It keeps producer reachability and adds an
owner's import only when the resulting graph stays acyclic. Tests compare 2,000
import decisions against independent whole-graph cycle detection, including
existing producer dependencies. SDK-only fallbacks remain available. Actual routing
must use a fresh configured dependency capture; no routes are enabled yet.
