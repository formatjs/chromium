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
BEP reports 166,786.67 compiler CPU-seconds (46.33 CPU-hours), and
48.61 CPU-hours across all actions. No OOM kills occur. Its archive fails
relocation: local sandbox input symlinks
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

## Allocated CPU capacity

A separate 257-source Blink probe on a 16-CPU/32GB workflow request reports
19 available CPUs. ABBA build times are 123.36/117.70s with 16 jobs and
110.89/111.30s with 19 jobs: 7.8% lower mean wall time. Compiler CPU work rises
7.4%, from 1,735.73s to 1,863.79s on average. Minimum sampled available memory
stays above 20GB. Each pass executes exactly 257 selected local compiles, with
no supporting recompiles. All object bytes and both archives match.

Supporting setup stays warm; deleting only the probe's validated object outputs
forces compilation without changing compiler commands. These measurements do
not establish a complete cold-build speedup. The separate strict-cold trial at
`67a544d` tests 19 jobs with fresh state, dependency archives only and RBE off.
It [hits the hosted free-tier limit](https://formatjs.buildbuddy.io/invocation/9f80e2fc-3f69-4a9a-bd56-e477c4a7d46c)
after 3,602.15s. Runner usage is 59,171.49 CPU-seconds and 17,541,894,144 bytes
peak memory. No browser archive completes. This does not meet the cold goal.

The retained streaming profile survives the kill. Its partial trace contains
213,123 complete events, including 16,436 completed compile spans totaling
45,460.82 action task-seconds. These are recorded spans, not a complete count
of executed compiles or CPU usage. Remote execution task spans are absent.
The timing verification gate correctly returns false. The last visible progress
is 74,782/102,633 actions; that fraction cannot establish remaining build time.

Local subprocess attribution records 40,494.98s inside C++ compiler subprocesses
and 2,504.66s creating their sandboxes. Their containing action spans total
45,279.13s. Python generator subprocess spans total 13,957.48s, including Blink
bindings; the longest bindings action takes 569.83s. These are overlapping wall
task sums from the incomplete trace, not CPU totals, complete action counts,
or estimates of remaining work. Preserve that distinction when choosing the next
optimization; the partial generator/compile ratio is not a full-build ratio.

## Compiler training lead

The published LLVM 23.1.2-2 compiler's provenance points to hermetic-llvm
commit `35bd1a8`. Its [release packager](https://github.com/hermeticbuild/hermetic-llvm/blob/35bd1a85beead3d12dbb8f9a54ebe94aa7e3c724/prebuilt/llvm/llvm_release.bzl)
uses stage 3, which already applies ThinLTO and FDO. The
[training corpus](https://github.com/hermeticbuild/hermetic-llvm/blob/35bd1a85beead3d12dbb8f9a54ebe94aa7e3c724/toolchain/bootstrap/stage3/BUILD.bazel)
is Zstd C and freestanding C; the workload helper accepts C/header inputs and
uses the C compile action. Representative C++ training is an unmeasured lead
for the observed frontend cost. Any experiment needs a pinned compiler archive,
unchanged LLVM source/version and target flags, and complete output validation.
Do not rebuild the compiler inside the strict-cold browser timing trial.

The [separate compiler preparation](https://formatjs.buildbuddy.io/invocation/1faf4bbd-dd69-4aea-a088-6ea124411c54)
at `89fcfb7` adds C++ training to the pinned release source. It uses the original
Bazel 9.3.0rc2 release settings and LLVM 22.1.4 bootstrap seed; the compiler being
built remains LLVM 23.1.2. Upstream credentials and service endpoints are removed.
The first attempt fails because the new C++ training link omits libc++ runtime
archives. Fix `366173f` adds the toolchain's static runtime libraries to the link
command and declared inputs. Real action analysis confirms libc++, libc++abi and
libunwind; 183 Python tests pass.

The [corrected preparation](https://formatjs.buildbuddy.io/invocation/a1727b10-69a4-4d17-af3b-d4bf494e8ab0)
completes in 619.06s using cached RBE. Archive
`llvm-23.1.2-linux-amd64-cxx.tar.zst` has SHA-256
`adbc348d20518481b44be46c21440c8aec541572014a86614248c3db2b46cc5c`.
This is compiler preparation, not a cold browser result.

A same-compiler execution control compares six fixed V8 sources in separate
Bazel states. Two warmups then four ABBA passes produce identical six objects
and three archives. Every measured pass executes exactly six local compiles.
Mean wall times are 23.390s and 23.283s: 0.46% control variation, not a speedup.
An additional analysis guard verifies the actual compiler binary hash and
identical expanded commands before measurement.

The [trained compiler comparison](https://formatjs.buildbuddy.io/invocation/f330b1a3-51e4-46e4-963d-aae14ff9033d)
at `27c08bd` completes successfully. Four measured passes execute exactly six
local compiles each. Baseline wall times are 34.13/40.00s; candidate times are
28.00/28.15s. Means fall from 37.07s to 28.08s (24.3%). Compiler CPU means fall
from 131.96s to 101.02s (23.4%). Six objects and three archives match every pass;
expanded commands and environments match. Supporting state stays warm. This is
not cold-build proof or a full-browser speedup estimate.

The downloaded archive's 365 entries match upstream except `bin/llvm`; builtin
headers, tool symlinks and all other files match. Compiler binary hashes differ
as required. No replacement compiler has been adopted on main. Full browser
payload, ABI and rendering validation remain required. Keep the current
16-CPU/32GiB tier; no larger hardware test is authorized.

## Bounded Blink workers

The generator experiment at `2200a93` adds an explicit upstream worker-count
argument. Opt-in counts 2/4 reserve matching Bazel CPUs and 1/2GiB of action
memory; default remains serial. No global CPU-count override. Real action
analysis confirms four-worker arguments and all 5,574 outputs. Pinned-source
patch application, Python compilation, buildifier and 179 tests pass.

On the local 16-CPU-quota host, measured serial ABBA passes take 208.14/203.41s;
four-worker passes take 53.87/52.64s. Means fall from 205.78s to 53.25s (74.1%
action wall time). All 5,574 files match in both warmups and all measured passes.
Process observation finds one serial generator or four workers plus parent.
Supporting state stays warm; these timings do not establish full cold speedup.

Strict-cold integration `2c0c81a` combines this opt-in with the SHA-pinned compiler,
native tool sharing and 19 jobs. Fresh-state and cache-disable checks stay
unchanged. That public-index configuration has not run. The compiler prerelease
is now published after explicit user approval; the live combined trial below
uses the same archive through the private dependency handoff.
The strict-cold under-one-hour goal remains unmet; other four triples' strict-cold
timings remain unmeasured.

The combined configuration preflight at `2c0c81a` passes actual Bazel analysis:
six expanded compiler commands/environments match, expected original/trained
binary hashes are selected, and four-worker bindings declare all 5,574 outputs.
This disposable analysis fixture uses verified local archive URLs; it publishes
nothing and executes zero build actions.

An independent
[full worker-only strict-cold trial](https://formatjs.buildbuddy.io/invocation/c37119b8-bbea-4d36-b30f-82c8a2cdb53e)
at `c92f1eb` is running. It retains the original published compiler and tests
the validated generator change with the full archive target and existing
strict cache policy. No completed cold result or artifact is available yet.

## Private compiler dependency handoff

The [CI-only handoff](https://formatjs.buildbuddy.io/invocation/5551fe15-a956-45d5-b50c-09560bb37d1f)
at `f70d82a` succeeds using BuildBuddy's supported managed workflow API auth.
It fetches the pinned compiler archive from its existing CI artifact store and
checks exact size/SHA256. Credentials are neither printed nor extracted from RC
files. No public release is required for this benchmark; the earlier public
publication request was separately approved and completed.

Protocol `b45e37c` accepts that explicit compiler archive input, checks cached
archives too, generates a root LLVM index from a committed upstream template,
and records configuration hashes. It retains fresh output/install/user/auxiliary
state. Compiler fetch/setup time counts. A successful build must match the actual
compiler binary digest as well. Default builds retain the published compiler.
182 tests pass, including corrupt archives, unrelated host-index preservation
and wrong compiler rejection. Actual Bazel preflight confirms six identical
expanded commands/environments, the intended binary hash, four workers and all
5,574 bindings outputs. No build actions execute in this preflight.

The [combined strict-cold trial](https://formatjs.buildbuddy.io/invocation/4a088b2c-e46e-468a-95ee-e20ff5e1914a)
ran alongside the worker-only trial in separate workflows. Each requested
the current 16-CPU/32GB tier. This overlap prevents an isolated full-build wall
A/B claim; it does not relax timing, cache-policy or artifact acceptance gates.
Neither trial has produced a verified complete result yet.

## Published experimental compiler and scheduling probe

[Experimental compiler prerelease](https://github.com/formatjs/chromium/releases/tag/llvm-23.1.2-cxx-training-1)
contains the 39,193,174-byte archive, checksum and provenance. Anonymous download
SHA256 matches `adbc348d20518481b44be46c21440c8aec541572014a86614248c3db2b46cc5c`.
Publication does not change either running cold trial.

The scheduling probe compares jobs equal to CPU capacity against twice that
capacity, keeping the Bazel CPU resource budget fixed. It reruns only 257 owned
compiles in ABBA order; every object and archive must match. Supporting state
stays warm. The initial probe failed during target loading because its bounded
source API was missing. Revision `ecc5308` restores that API; real Bazel analysis
confirms exactly 257 unique owned outputs, and 183 Python tests pass. The
[retry](https://formatjs.buildbuddy.io/invocation/93ece4b2-8324-4b01-9023-c11d15225d6c)
completed. No scheduling improvement is established; measurements follow below.

The worker-only strict-cold trial hit the hosted one-hour limit after 3,601.21s.
No browser archive completed. Outer runner usage reports 60,724.57 CPU-seconds
and 19,409,952,768 bytes peak memory. Its streaming partial profile is being
collected; progress counters do not estimate remaining work. The trained-compiler
trial also timed out; measurements follow below. Neither establishes an under-hour build.

Full archive dependency analysis inventoried 52,516 `CppCompile` actions owned by
`cc_library`/`cc_binary` targets. This is a query subset, not an executed count.
All inventoried object outputs use PIC; no PIC/non-PIC duplicate variant was
found. Source multiplicity alone cannot justify sharing across configurations
or libraries. No further sharing change is adopted from this analysis.

The worker-only timeout's partial trace contains 225,741 recorded events and is
explicitly incomplete. Recorded compile subprocess spans sum to 41,978.70s;
compile sandbox spans sum to 2,046.45s. Recorded Python subprocess spans sum to
11,678.55s. The longest recorded bindings action is 121.77s. These overlapping
span sums are neither CPU usage nor full executed-action counts. Compiler work
still dominates; this trace does not establish end-to-end generator speedup.
The workflow wrapper's cache statistics do not describe the separate local cold
Bazel invocation. No final cold report or completed archive exists for this run.

## Trained compiler cold result and remaining experiments

The trained-compiler/worker4 strict-cold trial also hit the hosted cap: 3,601.11s,
61,118.79 CPU-seconds, 19,340,308,480 bytes peak memory. No archive completed.
Its partial profile is being collected. The six-source compiler gain has not
translated into a verified complete cold result.

Fixed-CPU scheduling ABBA completes at `ecc5308`. At CPU budget 19, jobs 19
takes 94.71/91.55s; jobs 38 takes 93.35/92.75s. Means differ only 0.08%. Each
measured pass executes exactly 257 compiles, with identical objects and both
archives. No supporting compiles rerun. Retain 19 jobs; no meaningful gain.

An actual trained-compiler Blink trace matches its sandboxed object bytes.
Frontend time is 2.67s of 2.70s; backend is 0.007s. Eight-source direct ABBA with
upstream `build/precompile.h` matches all 32 sandboxed baseline objects. Fresh
PCH preparation counts in both candidate phases: mean wall falls 32.70s to
30.38s (7.1%), CPU 32.21s to 30.32s (5.9%). This warm diagnostic does not prove
cold or complete-browser improvement.

Prototype `9810505` declares PCH/compiler/header inputs and passes sandboxed PCH
generation. Clang rejects a mismatched RTTI consumer. Full 256-consumer byte
checks run in separate fresh local state after a wrong-workspace diagnostic was
discarded. No browser rollout. Full payload, ABI/rendering and strict-cold gates
remain mandatory. Other four triples' strict-cold timings remain unmeasured.

The trained trial's collected trace is incomplete (214,913 events). Recorded
compile subprocess spans sum to 42,276.18s, compile sandbox spans 1,963.65s and
Python subprocess spans 11,967.13s. These overlapping sums are not CPU totals,
full executed counts or an isolated comparison with the worker-only trial.

## Sandboxed standard PCH correctness

Prototype `e4cd0cd` matches all 256 original object hashes and the cohort archive
(`4a346e0ea2f9d63adfe21ceade07f671006b4653476f487c1f92aeac5ee2fb90`).
Actual trained compiler hash is verified. No complete-browser or cold claim.

Independent sandboxes exposed absolute PCH paths and project-header shims hidden
inside the AST. The corrected producer uses the fixed upstream standard header,
hermetic toolchain includes, `--relocatable-pch` and an explicit build-root
sysroot. Consumers declare the original header. Full Clang validation remains
on. Actual action analysis finds 1,730 inputs; the upstream header is the only
Chromium input. Driver expansion confirms all six standard include roots are
managed toolchain paths.

The first BB harness failed before compilation because its compiler verifier
read execroot links before execution created them. A regression reproduces the
failure, then passes using the fetched repository path. All 186 tests pass;
actual controller preflight verifies equivalent 256 consumer commands, output
inventories and compiler. The [corrected fixed-resource benchmark](https://formatjs.buildbuddy.io/invocation/e7bff94b-b8e7-4c95-90ea-b6e297872f53)
is running. PCH generation must rerun in each candidate phase. No timing gain is
accepted before that report passes all execution and byte checks.
