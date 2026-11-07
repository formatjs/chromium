# Chromium CI

`buildbuddy.yaml` cross-builds five platform bundles on hosted Linux workers.
Each successful BuildBuddy status triggers `cross-compile.yml`, which downloads
that platform's archive and SHA256 through the BuildBuddy API. It then calls
`smoke.yml` on a matching native GitHub runner. Smoke checks commit, version and
executable architecture before running the relocated browser against a local
HTTP page. No browser rebuild happens in GitHub Actions.

[Rendering checks](rendering/README.md) also compare screenshots of two local
fixtures with reviewed PNGs. Each native job preserves actual, expected and diff
images plus its rendering report, including failures.

The handoff follows [FormatJS's native smoke workflow](https://github.com/formatjs/formatjs/blob/main/.github/workflows/native-smoke.yml).
Only `buildbuddy-io[bot]` statuses with known platform names enter the handoff.
The downloader and smoke scripts come from the default branch. Downloads require
a successful, complete invocation matching the repository, commit and action;
artifact names, hosts, size and SHA256 are checked before upload to GitHub.
Separate status jobs report each native smoke result on the original commit.

Build targets use `with_cfg` to select hermetic LLVM platforms:

```sh
bazel build --config=browser //tools/ci:linux-amd64
bazel build --config=browser //tools/ci:linux-arm64
bazel build --config=browser //tools/ci:darwin-arm64
bazel build --config=browser //tools/ci:windows-amd64
bazel build --config=browser //tools/ci:windows-arm64
```

Host generators retain their execution platform. Both Windows targets use MSVC.
CI enables the approved MSVC runtime and Windows SDK license flags when fetching
their toolchains.

The linked BuildBuddy GitHub App supplies build credentials through its Bazel
wrapper. Remote cache, execution and BES use `formatjs.buildbuddy.io` with
`--config=buildbuddy`. Artifacts upload through `BUILDBUDDY_ARTIFACTS_DIRECTORY`.
GitHub downloads reuse the existing organization secret
`BUILDBUDDY_RO_PUBLIC_KEY`, already available to this repository. No new API key
or GitHub write token is needed. Pull requests build without merging the base
branch so artifact provenance matches the reported commit.

All five full browser builds and native rendering checks passed on `8e59628`.
macOS and Windows use the same Linux cross-build and native smoke handoff.

Component builds also run in BuildBuddy, one action per platform. Their archives
include Rust and Expat probes; macOS and Windows additionally include allocator,
base, Mojo, TCP, graphics, V8, Dawn, ANGLE and GPU probes, plus DXC on Windows.
`platform-components.yml` accepts only BuildBuddy statuses, verifies invocation
provenance and checksums, then executes downloaded probes on matching native
GitHub runners. GitHub Actions never invokes Bazel.

Linux runtime tests build remotely from a hosted BuildBuddy action and execute
on its Linux worker, including the private Xvfb integration test. Independent
compatibility consumers build in a separate BuildBuddy action so their own module
and toolchain configuration remains isolated. GitHub retains Python metadata
checks and native artifact smoke/rendering tests.

BuildBuddy timing profiles are available on each child Bazel invocation, rather
than the outer workflow run. `Profile BuildBuddy builds` collects action counts,
cache statistics and sanitized timing summaries for a commit; raw traces remain
in BuildBuddy.

Profiling `3b90aa7` found 155,835–202,264 registered actions per full browser
configuration. Warm browser builds took 324–512 seconds while executing only
one or two remote actions. Windows archive compression consumed 221–229 seconds.
Archives now cache the compressed bundle independently of the commit manifest.
Revision stamping prepends a deterministic gzip member, preserving the existing
tar layout, checksums and provenance validation without recompressing the bundle.
Bazel action keys were checked across two revisions: payload unchanged, stamp
changed. A 5.9 GB real DLL/PDB bundle took 138.6 seconds to compress locally;
reusing its 1.12 GB compressed payload took 1.3–5.7 seconds to stamp. Full CI
wall-time improvement still needs comparison after the new payload cache warms.

The compiler optimization pilot lives in `tools/ci/compile`. It forwards Blink's
real compilation context while compiling layout, SVG paint, CSS color, and
canvas probe sources, avoiding a full Blink library rebuild. CSS and canvas
sources cover the macro-closure and Khronos declaration failures found by the
first full-browser trial. Each source retains its owning library's flags. The initial
single-source action declared 76,130 inputs. The BuildBuddy experiment compares
baseline/scanner/scanner/baseline runs, records compiler input differences and
per-source timings, and requires identical archive bytes. Distinct unused macros
force every selected source to recompile; timing excludes generator preparation.
The full-browser trial enables the scanner flag in `--config=browser`, with only
Blink core libraries requesting its feature. Toolchain bootstrap and other
Chromium libraries keep their existing input behavior. Macro-selected Skia
headers remain mandatory inputs. The experiment branch runs browser builds and
Linux runtime coverage before rollout.

`--platform` selects any supported browser triple. Each cross-platform probe lives
in its own package and uses that platform's captured compilation context. Windows
uses the MSVC transition and accepts both SDK/runtime licenses, matching browser
CI. BuildBuddy runs the five comparisons; GitHub only collects sanitized reports.

The optional `--batch` host benchmark compiles 100 fixed common core sources plus
the canvas regression source. It warms both configurations before the timed
baseline/scanner/scanner/baseline sequence. Every source recompiles each run;
all six archive sets must match. Its dedicated `perf/compile-throughput` branch
runs only the throughput action, excluding the small regression jobs. Wait for
other browser rebuilds to finish before interpreting client CPU and execution
phase timings.

Next: reduce oversized header closures, audit host-library reuse where compiler
and ABI settings match, then benchmark client CPU and action concurrency. Rollout
requires representative compiler equivalence plus the five browser/native smoke
platforms; changing compiler options or snapshots is outside this experiment.

A host-reuse experiment replaced 21 matching Linux ARM64 snapshot Mojo
serialization targets with native providers. The isolated A/B graph check grew
from 83,734 to 84,278 registered C++ actions because those providers imported
additional dependency closures. That version was reverted. Future host sharing
needs a narrower seam and measured execution benefit before rollout.

The compiler pilot uses the browser's bounded-analysis settings and compact
execution logs to avoid flat spawn-log expansion in the 8 GB Bazel heap.
`bb explain` compares compiler inputs; timing comes from the selected C++ action.
The initial pilot exhausted that heap before the compiler comparison completed.

The first compact-log comparison produced identical archives but removed zero
inputs. Its single compiler timing pair (31.2s versus 21.8s) does not establish a
speedup. Bazel 9.2 requires both `--cc_include_scanning` and the requested
`cc_include_scanning` feature; the pilot now enables both in its scanner mode.
The feature belongs only to the probe rule: requesting it globally also scans
LLVM's glibc bootstrap and fails on its generated `config.h`.

See [PERFORMANCE.md](PERFORMANCE.md) for the measured compiler baseline and
optimization rollout order.
