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

This implementation compiles real source motion, but is not yet wired into the
workbench target job contract. Next integration must propagate the same oblique
basis into length, contact and depth evaluation and provide verified candidate
storage. Reusing front-view depth evidence would be invalid. Root translation is
reprojected; foot contact, target geometry and artwork remain to be evaluated.
No side/back texture reconstruction or torso mesh deformation is implemented here.
