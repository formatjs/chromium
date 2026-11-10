# Recover pinned BOLT preparation artifacts

The original public invocation manifests remain readable, but their snapshot
and execution-CAS download links return `NotFound`. Rebuild the same pinned
compiler, BOLT tool, profile merger and instrumentation runtime on the existing
16-CPU/32-GB BuildBuddy tier. Preparation may reuse RBE caches.

The relocation input guard stays unchanged. It previously rejected LLD moving
`.eh_frame` before `.rodata`; recovery does not turn that failure into acceptance.
Retain the failed report and fetch artifacts from the preparation child builds
for independent validation. No optimized compiler is adopted by this change.

A measured cold Chromium run still needs fresh checkout, install/output/user
state and tool caches, disabled RBE/action caches, complete timing/profile proof,
and native object, archive ABI and rendering validation.
