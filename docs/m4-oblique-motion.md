# Constant-yaw MotionIR candidates

`oblique_source.py` extracts world-space vectors and root positions from verified
BVH or validated SOMA77 inputs, expressed in the original declared camera basis.
`oblique_motion.py` applies a constant orthogonal yaw, recomputes projected
directions, parent-relative setup deltas and root translation together. It produces
an independent MotionIR and receipt; existing axis-only mapping formats and frozen
bundles are unchanged. The receipt identifies parent motion, spatial inputs, yaw,
precision and result. BVH uses 12 decimals and Kimodo preserves its 5-decimal
compiler precision. Degenerate projections fail explicitly.

Actual frozen eight-source tests compiled thirteen angles from -90 to +90 degrees
at 15-degree intervals. Zero-degree tracks reproduced the existing source transfer
within 1e-9 (the check stops the run otherwise). Smallest absolute qualifying yaws:

| Source | Yaw passing existing full-clip projection checks |
| --- | --- |
| Breathing | 0 |
| Walking | -45 |
| Raise arms | -30 (+30 also passes) |
| Turn | None |
| Squat | -60 (+60 also passes) |
| Boxing | None |
| Reach | +45 |
| Kimodo wave | 0 |

Selection here only minimizes deviation from the original view among angles that
pass the existing visibility and relative-length tests. It is not an aesthetic
score or an automatic target acceptance policy. Negative and positive yaws can
have different results because source poses and source artwork are asymmetric.

Reproduce with `tools/m4_oblique_candidates.py` and the frozen v3 plan; generated
MotionIR documents, receipts and summary are under
`../tmp/m4-motion-center/oblique-source-v1/`.

## Workbench target integration

Target requests now accept an explicit `projection` with profile
`constant-yaw-source-motion-v1` and `yaw_degrees` in [-90,90]. Omission retains the
existing behavior. Retry preserves this selection. The motion center exposes a
constant relative yaw selector only when the server advertises support; choosing
a different source resets it. No source or reviewed character artifact is replaced.

The worker compiles independent MotionIR, derives axial length ratios from the
same projection receipt, and recomputes source depth using the same yaw. Original
world-space source contact eligibility remains unchanged by camera yaw; target
support correction and geometry are evaluated again on the new candidate. The
receipt is part of the verified output inventory as `motion-projection.json`.

First actual target: Alice walking at -45 degrees,
`motion-650a3b14b51b49ec93638451f8474fee`, artifact
`6088dbcb780444e8a164a1d7dae15302ee55ba75abf2bcb6ba68b51ae475e2b7`.
It completed 377 official Runtime frames with geometry passing. Contact remains
`inferred_proxy_drift` and depth remains `depth_candidates_need_review`; this is
not an accepted motion. The independent side-view cohort continues separately.

Validation: 29 related backend tests and browser checks for explicit selection,
source-change reset and omitted-projection compatibility. No side/back texture
reconstruction or torso mesh deformation is implemented here. Current capture
and source projection success do not imply that front artwork looks correct
under every oblique motion.
