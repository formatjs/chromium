# Chromium build performance

Optimize measured compiler work first. Keep compiler flags, target ABIs, and
artifact smoke coverage intact. Compare the same workload and cache state;
registered actions are not executed compiles.

## Cold-build target

Target: under one hour per supported triple on BuildBuddy, including artifact
packaging. Preserve hermetic toolchains, declared inputs, compiler options,
target ABIs, and native rendering smoke coverage. Four strict cold targets finish under one hour; Darwin remains unverified. The `24375b5` cohort finished in 35m56s–46m04s and passed native
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
and bindings: 162 libraries with 7,604 source entries. Full Linux ARM64 validation
remains required. The other four browser captures contain no Blink-core libraries.

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

## Latest strict cold results

The `0046328` cohort uses fresh output bases verified against canonical Bazel
startup options, fresh repository download caches, zero reused actions, and
no in-flight action merging. Shared RBE CAS and worker caches remain uncleared.
Times cover the complete BB workflow, including setup, fetching, analysis,
linking, packaging, and artifact upload.

| Target | Complete BB workflow | Executed C++ compiles | Executed Bazel actions |
| --- | ---: | ---: | ---: |
| [Windows MSVC AMD64](https://formatjs.buildbuddy.io/invocation/6202aeb6-2d75-4407-9e91-3ac80d9b1daa) | 39m20s | 55,019 | 122,379 |
| [Windows MSVC ARM64](https://formatjs.buildbuddy.io/invocation/f7789787-5f26-447f-97bf-4d82cd13acf9) | 40m15s | 55,764 | 124,685 |
| [Linux AMD64](https://formatjs.buildbuddy.io/invocation/84679466-4338-459f-acf9-522ecec5efdf) | 42m43s | 75,286 | 154,750 |
| [Linux ARM64](https://formatjs.buildbuddy.io/invocation/14045122-03d4-4ab3-ab81-6eabbd0c2a7d) | 47m36s | 77,537 | 161,470 |

All four exact cold artifacts pass native ABI and rendering smoke. Windows
payloads, including PDBs, match same-commit normal builds byte-for-byte. Linux
comparisons verify the existing randomized NSS signatures while covering all
remaining tar bytes. Independent RBE metadata confirms 263,606 distinct,
completed, unmerged C++ outputs with no failed or incomplete compile records.

Darwin's `0046328` run repeatedly executes the same bindings action. Eight
executions complete successfully in roughly 3m30s each; this is not evidence of
a stuck generator or an OOM. The bounded upstream mode preserves output bytes,
but does not resolve this repeated work. An isolated `41b2719` trial uses Bazel
9.3.0 and enables input-recovery messages. Its full Darwin analysis passes, but the build then reports no space left on
device. The trial does not establish a rewinding fix. Both 200GB and 400GB disk
requests expose the same 93GiB filesystem; /tmp and workspace share that device.
Moving paths alone cannot resolve the capacity issue. A separate 03d46f1 trial
uses a fresh runner namespace with Bazel 9.2: 87GiB free and no managed output
base at startup. Cold completion and payload/native validation remain pending. Bazel 9.3 includes
[upstream rewinding fixes](https://github.com/bazelbuild/bazel/releases/tag/9.3.0);
a connection to this failure remains a hypothesis until the trial completes.

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

## Results so far

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
Four fresh-state targets pass. Darwin repeatedly completes the bounded producer;
runner state remains under investigation. Serial mode bounds resource use and
preserves outputs, but has not established a fix for Darwin's repeated work.
