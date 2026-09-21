# Kimodo local depth and large-motion projection

This experiment extends the existing local torso/limb depth checker to verified
SOMA77 observations. It does not change candidate draw order, weights, or approval.

## Source contract

`KimodoDepthSampler` validates the NPZ bytes, array inventory, redundant FK data,
and declared mapping before reading joint positions. Screen/depth basis and the
requested camera yaw determine depth, relative to the mapped upper spine and
normalized by the declared reference length. Hand depth uses the observed wrist
and middle-finger chain, including SOMA77's explicit terminal joint. This is a
chord proxy, not a reconstructed hand surface. BVH End Site tuples are not used.

The default accepts exact source ticks only. Explicit
`linear_observed_positions` sampling is an interpolation model, not an additional
observation or a guarantee of correct rotational motion between frames. Unknown
cloth helper depths remain unknown. No depth is fabricated for them.

## Reproduce

Run with `PYTHONPATH=src;tools` from the repository:

```powershell
python tools/m4_kimodo_local_depth_probe.py motion-76e0d141f979430db88de1183c46a79b ../tmp/m4-motion-center/kimodo-local-depth-alice-v1.json
```

The tool verifies the completed task, source bundle, and candidate identities;
checks every recorded arm/torso source-frame pair with sparse alpha sampling;
and preserves every unmeasured result. For a torso bake it reconstructs the
compensated virtual shoulder/pelvis origins at exact source keys, after matching
the stored shape receipt against a freshly derived source report. Unchanged bone
guides are not used as warped anchors. The default does not check intermediate
times. No mode captures new Runtime frames.

With `--midpoints`, the tool explicitly uses linearly interpolated source joint
positions and checks every adjacent source-frame midpoint. For warped candidates,
`BakedWarpPlane` reads the common deform-key schedule, verifies it against the
bake receipt, reconstructs virtual anchor offsets in each bone's local frame,
and interpolates these offsets before applying the current bone transform.
It rejects mismatched schedules, non-linear deform curves, and candidate reuse.
This differs from interpolating world positions or applying an ideal shape at
the query time. Tests compare against baked marker vertices, including a rotating
parent; 12 relevant tests pass.

Alice's same torso candidate was checked at all 238 arm/torso interval midpoints:
119 `uniform_back_proxy`, 119 `requires_partition_or_more_depth`, zero unmeasured,
10,873,815 sampled pixels. Report:
`../tmp/m4-motion-center/kimodo-warp-depth-alice-midpoints-v1.json`.
This supplements the source-frame evidence, not a continuous-time or Runtime
acceptance proof. Intermediate source depth is explicitly modeled, not observed.

Alice's original Kimodo wave candidate
`9fc3e02e74036b34322480c4936f5bfd874c8931bf11372e8c1c19fe2e0c486a`
produced 120 `uniform_back_proxy` and 120
`requires_partition_or_more_depth` records, using 10,351,264 sampled pixels.
The former is support under the local plane/limb proxy, not visual acceptance.
Eight sampler, source-identity, interpolation, and hand/BVH regression tests pass.

Huiye's original wave candidate
`8dd7feb7a42764d6bba8780ad4d8262fbcf25e6a35d6f733cd45acc7f88f46b8`
produced 172 `requires_partition_or_more_depth` and 68 unmeasured records
(`depth_overlap_pixel_budget`). The local checker consumed 63,999,290 of its
64,000,000 pixel budget. These failures remain in
`../tmp/m4-motion-center/kimodo-local-depth-huiye-v1.json`; they are not evidence
of correct ordering. Sparse coarse overlap success does not imply this more
expensive local check is complete.

The compensated-anchor check also ran on Alice's torso-baked wave candidate
`5423f18e0fc9f5270ca6b5354d87284c4384284e2e41507a87de8079cd86ac08`:
120 `uniform_back_proxy`, 120 `requires_partition_or_more_depth`, zero unmeasured,
10,972,397 sampled pixels. Evidence is in
`../tmp/m4-motion-center/kimodo-warp-depth-alice-v1.json`. Every measured record
includes the fitted plane and virtual anchor coordinates. Synthetic marker
vertices independently sampled from the baked mesh match these anchor positions.
All 14 relevant torso, local-depth, and Kimodo tests pass.

## Large-motion design

### Optional spatial interval refinement

`--pixelwise` selects `barycentric-pixel-depth-interval-v1-experiment` inside
each check. It evaluates the lower and upper vertex-depth bounds at opaque
pixel centres rather than assigning an entire triangle's min/max to each pixel.
The alpha mask, bilinear texture sampling, margin, and source depth assumptions
are unchanged. Unknown triangles and front/back overlap retain priority over a
single signed result. Raster/interval work is charged to the same finite budget.
Default checks retain the original whole-triangle policy.

On the same Alice torso candidate, 240 source-frame pair checks remain 120 back
and 120 unresolved, with no unmeasured records. For `layer-003`, summed ambiguous
pixel observations across 120 frames decrease from 156,296 to 142,297; back
observations increase from 34,945 to 48,944. There are zero front or unknown
observations in either run. These are repeated pixel observations, not unique
pixels or a statistical error rate. The first frame changes from 372 ambiguous
pixels to 141. Total budget used is 9,198,556. Evidence:
`../tmp/m4-motion-center/kimodo-warp-pixel-depth-alice-v1.json`.

This narrows the remaining issue to depth-margin ambiguity under the plane/limb
model; it does not justify an automatic front/back partition or a relaxed margin.
Twenty-three related tests cover interval gradients, unknown data, opposite
overlapping triangles, budgets, legacy depth checks and sparse sampling. No
candidate, draw order, or Runtime acceptance is changed by this experiment.

### Official same-frame review capture

`tools/m4_local_depth_capture.py` reads a diagnostic and its exact stored candidate,
selects the first, maximum-ambiguity and last unresolved time per attachment pair,
and performs a fresh official WebGL/SwiftShader capture. It preserves skeleton,
atlas, textures and draw order. A separate immutable capture bundle holds only
the selected numeric references; it does not replace the source candidate.
Image crops use the recorded framebuffer origin and dimensions, with checked
world-to-image coordinates. Reports bind the diagnostic, candidate, skeleton,
capture bundle, source times, full images and crops by hash.

Alice's pixel-interval report produced three new captures at 0, 3.166667 and
3.966667 seconds, with maximum numeric error 0.00007090526301690037 pixels.
Review page: `../tmp/m4-motion-center/local-depth-runtime-alice-v1/index.html`.
The cropped region is the attachment-pair overlap bounding box, not a claim that
every pixel in the crop is ambiguous. It includes other visible character parts
from the actual complete framebuffer. Two tests cover the coordinate conversion
and representative-time selection. Capture passes do not establish anatomical
depth truth, correct visual order, or human acceptance.

### Three-structure local-depth evidence

The same pixel-interval strategy ran without parameter changes on Alice,
Hongmeiling and Huiye's frozen torso-baked Kimodo wave candidates. Exact report,
skeleton and artifact hashes are frozen in
`benchmark/m4-local-depth-cohort-evidence-v1.json`.

| Character | Pair/frame samples | Main causes | Pixel budget used |
| --- | ---: | --- | ---: |
| Alice | 240 | 120 back, 120 depth-margin ambiguity | 9,198,556 |
| Hongmeiling | 480 | 199 no overlap, 281 depth-margin ambiguity | 4,302,720 |
| Huiye | 240 | 185 missing depth support, 55 unmeasured budget failures | 63,834,112 |

Missing depth takes priority in cause labels; the separate front/back/ambiguous/
unknown pixel counts retain mixed evidence. Unknown or unmeasured samples never
enter a correct/accepted denominator. The summary rejects duplicate samples and
nonconserving pixel inventories. Two tests cover these distinctions.

New official captures supplement the earlier Alice capture: Hongmeiling has
4 distinct times / 8 pair crops, maximum error 0.00010115556942487207 px; Huiye
has 5 times / 6 crops, maximum error 0.00012122095011158246 px. Review folders are
`../tmp/m4-motion-center/local-depth-runtime-hong-v1` and
`../tmp/m4-motion-center/local-depth-runtime-huiye-v1`. These representative
captures do not cover Huiye's 55 unmeasured records. They leave draw order and
acceptance unchanged. This wave-only experiment supplements, rather than
replaces, the frozen eight-motion cohort and its unresolved failures.

### Projection and rotation strategy

Use three distinct channels rather than applying a single 2D rotation to all art:

1. **Torso orientation:** project shoulder and pelvis anchors into the chosen
   view. Remove roll already represented by the rig, then derive relative width,
   height, and shear for a local deform. Preserve attachment connections through
   the compensated bake. The existing bounded torso experiment implements this
   first approximation; it does not reconstruct side or back artwork.
2. **Occlusion and foreshortening:** use local arm/hand versus torso depth in
   overlapping opaque regions. A limb crossing the torso can need separate
   upper-arm, forearm, and hand ordering. Cloth needs its own model. Add temporal
   hysteresis only where the depth evidence supports a stable decision.
3. **Rotation continuity:** distinguish angle wrapping, projected-axis collapse,
   genuine circular motion, and axial twist. Unwrap well-sampled screen angles;
   preserve genuine winding. Near an axis pointing at the camera, rely on source
   orientation and temporal constraints rather than unstable `atan2` alone.
   Axial twist needs orientation-driven mesh deformation or alternate palm/back
   attachments, not repeated planar rotation of a flat hand texture.

Full side/back turns require view-specific art or another representation. A
single front image cannot supply newly visible surfaces. Unsupported spans must
remain explicit; never hide them by modulo-clamping rotation, silently freezing
poses, or relabeling unknown cloth depth as a successful check.

Next integration requires intermediate-time validation and same-frame Runtime checks before local ordering
can be adopted. This experiment alone does not complete M4.
