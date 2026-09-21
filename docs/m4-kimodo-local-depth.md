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
and preserves every unmeasured result. It rejects candidates with a torso bake:
their unchanged bone guides cannot yet represent the warped surface for this
checker. It does not check intermediate times or capture new Runtime frames.

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

## Large-motion design

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

Next integration requires consistent depth anchors after torso deformation,
intermediate-time validation, and same-frame Runtime checks before local ordering
can be adopted. This experiment alone does not complete M4.
