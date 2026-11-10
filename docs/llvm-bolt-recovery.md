# Recover pinned BOLT preparation artifacts

The original public invocation manifests remain readable, but their snapshot
and execution-CAS download links return `NotFound`. Rebuild the same pinned
compiler, BOLT tool, profile merger and instrumentation runtime on the existing
16-CPU/32-GB BuildBuddy tier. Preparation may reuse RBE caches.

The relocation input guard stays unchanged. It previously rejected LLD moving
`.eh_frame` before `.rodata`; recovery does not turn that failure into acceptance.
Retain the failed report and fetch artifacts from the preparation child builds
for independent validation. Retain both preprocessing inputs, original metadata
and dependencies, normalized replay flags and checksums before the long compiler
step starts, in a sibling artifact directory. Compiler failure still propagates. No optimized compiler is adopted by this change.

A measured cold Chromium run still needs fresh checkout, install/output/user
state and tool caches, disabled RBE/action caches, complete timing/profile proof,
and native object, archive ABI and rendering validation.

Recovery workflow reached LLVM profile preparation, then retried internally. Its
last attempt failed fetching the pinned Chromium archive with `Read timed out`.
Preparation now uses Bazel’s `--http_timeout_scaling=3`; source URLs, checksums
and compiler flags stay pinned. This does not change the strict-cold harness.
