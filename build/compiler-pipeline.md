# Compiler pipeline probe

Compare jobs equal to reported CPU quota against twice that job count. Keep
local CPU and memory resources fixed. Extra in-flight actions may overlap input
preparation; CPU saturation or memory contention may erase the gain.

The probe uses the pinned trained compiler, private RAM sandbox and normal
Chromium flags. Supporting state stays warm. Delete only the 257 inventoried
probe objects, then run ABBA. Each measured pass must execute exactly 257 real
local compiles without supporting recompiles. Every object and both archives
must match. Actual compiler hash is checked; no action-key seeds or command edits.

This is a scheduling microbenchmark, not cold-build proof. No scheduling change
is applied to either live full-cold trial. Current 16-CPU/32GB tier retained.
