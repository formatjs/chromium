# C++-trained compiler experiment

Root LLVM index changes only the Linux AMD64 execution compiler archive. Other
host archives and all Chromium target flags stay unchanged. Compiler stays LLVM
23.1.2, built from hermetic-llvm source `35bd1a8` with the original release
settings and added C++ FDO workload. Preparation source/patch is commit
`366173ffc47d1a12a92c32d542c39c24b80fea28`.

Archive SHA256:
`adbc348d20518481b44be46c21440c8aec541572014a86614248c3db2b46cc5c`.
All 365 package entries match upstream except `bin/llvm`; resource headers and
tool symlinks match. Actual compiler SHA256 changes from `6538459` to `d94fff1`.

[Six-source V8 ABBA](https://formatjs.buildbuddy.io/invocation/f330b1a3-51e4-46e4-963d-aae14ff9033d)
executes exactly six local compiles per measured pass. Expanded commands and
six object/three archive bytes match. Mean wall time falls from 37.07s to 28.08s;
compiler CPU falls from 131.96s to 101.02s. Warmups compile 2,708 supporting
objects per variant; neither those warmups nor this probe is cold-build proof.

Bounded Blink generation independently reduces measured mean action wall time
from 205.78s to 53.25s on the local host. All 5,574 files match across two warmups
and ABBA passes. Four workers plus parent observed; Bazel reserves four CPUs.

Full strict-cold trial uses both changes, 19 jobs and the existing fresh-state
protocol. Only fetched dependency archives may be reused. Compiler preparation
happens separately and is excluded from the browser trial, like the upstream
prebuilt compiler's preparation. RBE, action, disk, remote and repository-contents
caches stay disabled. Full browser payload/ABI/rendering remain unverified.
Other four triples' strict-cold timings remain unmeasured.

Public compiler prerelease publication is pending explicit approval. Do not
launch this index until its pinned archive URL is available and verified.
Experimental branch only; main remains unchanged.
