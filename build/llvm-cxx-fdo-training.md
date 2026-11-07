# C++ compiler training experiment

Experimental. No measured compiler speedup or replacement archive yet.
Normal browser builds still select the existing prebuilt compiler.

The pinned LLVM 23.1.2-2 release already uses ThinLTO, FDO and Mimalloc.
Its FDO corpus contains C sources; our sampled V8 compiles spend 79% of
compiler time in the frontend. This patch adds standard-library and
template-heavy C++20 training alongside the existing C corpus.

```mermaid
flowchart LR
  Seed[Prebuilt seed] --> First[Stage 1 compiler]
  First --> Second[Instrumented stage 2]
  Second --> Profiles[C and C++ training profiles]
  First --> Final[Stage 3 compiler archive]
  Profiles --> Final
  Final --> Check[Output and timing checks]
```

Build the compiler in a separate workspace pinned to release source commit
`35bd1a85beead3d12dbb8f9a54ebe94aa7e3c724`, with this patch. Keep its original
compiler build settings; Chromium's hardening options must not alter the
compiler comparison. Change training inputs only, preserving LLVM source,
version and browser compiler flags.

Before adoption, compare fixed C++ workloads with both compilers, then verify
the complete browser payload, ABI and rendering. Publish and pin a compiler
dependency archive only after these checks. Rebuilding LLVM inside the cold
browser trial would add compiler preparation work to the requested measurement.

Current validation: patch applies to both pinned module and release sources;
corpus passes Clang 23.1.2 with hermetic headers; Bazel analysis declares the
stage-2 C++ compile action and compiler profile output. This does not prove
profile generation, a successful compiler bootstrap or a performance gain.
