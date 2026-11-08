# Include context probe

Clone the original header/define context. Keep the owner's complete GN include
list, registry/toolchain roots and forwarder interfaces. Remove other inherited
Chromium directories. Default builds stay unchanged.

The checked-in GN snapshot has 63 flattened include roots, including dependency
public configs. The legacy library table retained only 14. Using that smaller
list failed on PartitionAlloc's public source root. No missing-directory
exceptions were added; the corrected list comes directly from the snapshot.
`include_context_roots.bzl` records its checksum.

Actual arguments shrink from 941 include paths to 782. All 256 commands preserve
other flags/environments and retained include order. A real sandboxed build
executes 256 compiles; all original objects and archive bytes match. Same trained
LLVM hash. This is correctness proof, not a timing or cold result. Local ABBA uses matching native baseline flags and private RAM sandboxes;
results follow below.

```mermaid
flowchart LR
  GN[Complete GN include list] --> Context[Projected compile context]
  Registry[Registry and toolchain interfaces] --> Context
  Headers[Original headers and defines] --> Context
  Context --> Compile[Compile original sources]
  Compile --> Bytes[Original object and archive checks]
```

Evidence:

- `/tmp/chromium-include-context-full-roots-preflight.json`
- `/tmp/chromium-include-context-command-proof.json`
- `/tmp/chromium-include-context-full-roots-correctness.json`
- `/tmp/chromium-include-context-abba-001/report.json` when complete

The rejected 14-root attempt is preserved in
`/tmp/chromium-include-context-14-roots-failure.log`.

The accepted local comparison uses a native baseline with exactly matching
non-include flags, private 8 GiB RAM sandboxes, 16 CPU quota, 6 GiB JVM and 24 GB
action memory. Baselines: 67.338 s, 60.730 s. Candidates: 55.269 s, 55.922 s.
Means 64.034 s versus 55.596 s: 13.18% wall reduction, 2.10% compiler CPU
reduction. Every measured phase executed 256 compiles and checked all original
object/archive bytes and source subprocess traces. Baseline drift remains.
Report: `/tmp/chromium-include-context-ram-abba-001/report.json`.

The earlier disk comparison is not accepted: its borrowed PCH baseline had an
extra relocation sysroot flag. The new native baseline removes that confound.
BB confirmation and full cold measurement remain pending.
