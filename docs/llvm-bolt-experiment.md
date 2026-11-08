# LLVM BOLT experiment

Tool preparation only. No browser compiler adoption or cold-build result.

The stripped Chromium-trained LLVM lacks relocation records required by BOLT
instrumentation. Prepare an unstripped compiler from the same pinned source,
then add `--emit-relocs` only to its Stage 3 link. Preserve upstream patches,
source exclusions, bootstrap compilation and training inputs. The FDO selector
uses the canonical root label: native option matching does not resolve the
apparent `@llvm` spelling.

Before accepting that input:

- Compare every compiler compile/link command and environment. Permit only the
  extra relocation option on the final compiler link and its LTO indexing action.
- Compare loaded ELF sections, segments and mapped bytes. Only nonloaded metadata,
  section-table bookkeeping and the GNU build ID descriptor may differ.
- Require symbols and text relocations. Build LLVM's instrumentation runtime with
  native objects using its upstream Linux x86_64 flags and the hermetic SDK.

The runtime and compiler remain CI artifacts. A later experiment must collect
profiles, test compiler outputs and measure speed before adoption. Preparation
uses normal RBE caches; it is never evidence of a strict-cold Chromium build.

The relocation build passed the 64,253-action command comparison but failed the
strict loaded-image guard. LLD creates the synthetic unwind section earlier when
copying relocations, moving `.eh_frame` ahead of `.rodata`. The guard remains.
The quarantined input reproduces 30 ordinary, 18 PCH and two training objects;
that supports further profiling, not production adoption or a cold-build claim.

Static instrumentation needs a periodic dump. Use cumulative counters so its
watcher writes the complete profile after the compiler exits. Build upstream
`@llvm-project//bolt:merge-fdata` through the same hermetic toolchain to combine
profiles. Do not substitute a custom profile merger.

[LLD relocation section creation](https://github.com/llvm/llvm-project/blob/llvmorg-23.1.2/lld/ELF/LinkerScript.cpp)
