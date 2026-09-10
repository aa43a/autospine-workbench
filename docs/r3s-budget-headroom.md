# R3-S joint-constraint budget allocation

The reviewed Bayunlan right sleeve retained 29 failed samples in each of two
combined motions. Four hanging-cloth triangles (301/324/325/346) failed at keys
as well as between keys; this was not only an interpolation problem. Unknown
triangle 255 did not adjoin a failed triangle in the recorded diagnosis.

At combined_mp sample 32 the area/edge lower-bound allocator provided 18.7412 px,
while two affected vertices used 18.7328/18.7344 px. The existing hard cap was
62.4707 px. Individual-constraint displacement bounds are necessary but do not
guarantee that neighboring constraints can be satisfied together.

An explicit headroom fraction now allocates part of the unused existing cap:
`allocated = estimated + fraction * (cap - estimated)`. Default zero retains
historical behavior and receipt fields. Values are validated within [0, 1];
the experiment CLI accepts only 0, 0.5 or 1. Ownership, fixed vertices, topology,
weights, motion ranges and geometry thresholds are unchanged.

With fraction 0.5, candidate
`96917265977bffa72ec22c765e13762b29684d40c85df02a3c2aa96ee5cfd22f`
passes all 14 retained motion tracks. All gates, unchanged bind data, fixed
vertices and per-key budget limits were read back and verified. The left tracks
were preserved. This is a generic policy with no character-name conditions.

Both sleeves pass 3,598 Spine 4.3.26 interpolation samples and official
spine-core 4.3.13 samples (maximum error below 0.000084 px). Official
spine-webgl 4.3.13 / ANGLE SwiftShader captures cover 3,598 frames and 345,408
contact probes with zero blank failures. Capture and image hashes were verified.
Review: `tmp/r3s-joint-headroom-runtime/index.html`.
No software-visible overlap peak captures were generated; this does not prove
whole-surface visual quality or confer human approval.

## Ordinary workflow

The new `repair` stage follows `cuff` and precedes `spine`. It tries at most two
allocations (0 then 0.5), each with at most three retained solver passes. Trials
and their source addresses remain available under the stage output. Passing
inputs are copied byte-for-byte without invoking the solver; failed candidates
remain subject to target and Runtime admission. The workflow engine identity
includes both repair tools, so historical checkpoints are not reused across this
change. Original Huiye/Uuz four-sleeve cuff artifacts were verified byte-identical
through this new stage.

102 sleeve tests and three source-size checks pass. Budget tests cover invalid
values, unchanged default evidence, and the existing cap; prior similarity and
area/edge-bound tests also pass. Full ordinary Bayunlan rebuild is recorded under
`tmp/r3s-automatic-repair`, run
`run-8bd79d59fbf8a2f62b19e24908f9c87d7bf17549b684f713c3906e86f891d59d`.
It completed all 14 steps, including official core and framebuffer checks,
with both sleeves exported and status `needs_review`. The repair stage produced
the exact experiment address above. The derived timeline link was then corrected
to select the completed repair stage (tested independently); numerical receipts
and assets were not regenerated or changed by that view-only correction.
