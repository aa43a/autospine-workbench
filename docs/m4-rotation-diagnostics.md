# M4 source rotation diagnostics

`targets/character43/rotation_diagnostics.py` inspects projected limb direction
from verified BVH FK or validated SOMA77 positions. It does not modify motion.
The command `tools/m4_rotation_probe.py` binds results to the frozen source job,
source bytes, view, MotionIR identity and cohort-plan digest.

The first actual front-view eight-motion run produced these limb-frame samples:

| Motion | Angle branch crossing | Direction unreliable (visibility < 0.2) |
| --- | ---: | ---: |
| Breathing | 0 | 0 |
| Walking | 2 | 64 |
| Raise arms | 0 | 23 |
| Turn | 4 | 0 |
| Squat | 2 | 0 |
| Boxing | 0 | 1 |
| Reach | 0 | 20 |
| Kimodo wave | 0 | 0 |

These counts are not distinct bad frames, rendered defects or failure rates.
Multiple limbs may contribute at the same source frame. A branch crossing is
normally harmless after continuous-angle interpretation. The report does not
prove target local rotations, skinning or interpolation are correct.

Continuity is reset across low-visibility samples. Exact half-turn differences
are ambiguous rather than assigned an arbitrary winding direction. Multiple
well-sampled turns are retained; rotations exceeding half a turn between source
samples cannot be uniquely reconstructed from endpoint directions. Axial twist
requires source orientation information and is outside this positional probe.

Six regression tests cover branch crossing, two complete turns, degenerate gaps,
half-turn ambiguity, invalid inputs and real BVH extraction. The actual run also
exercised the validated Kimodo adapter. Reports reside in
`../tmp/m4-motion-center/rotation-probe-v1/`.

Next: correlate source events with exported target local rotations and Runtime
frames, then add bounded visual adaptation. This probe alone does not repair
side-turn artwork, infer hidden pixels, or approve a candidate.

## Exported rotation correlation

`rotation_transfer_diagnostics.py` now compares the actual exported candidate
against the declared signed MotionIR-to-Spine local rotation transfer. It samples
the union of source and target linear key times and their midpoints, rejects
mismatched time ranges, and retains absolute differences rather than reducing
them modulo 360. Source projection events accompany each corresponding bone.
Missing tracks or nonlinear curves fail explicitly. This is numeric correlation,
not an additional framebuffer or visual acceptance test.

`tools/m4_rotation_transfer_probe.py` reads the exact candidate through the public
verified player endpoint. Actual front walking and turning were checked on Alice,
Huiye and Hongmeiling (six candidates). Walking's eight limb tracks match the
declared transfer exactly. Turning's arm tracks also match; left-leg differences
are approximately 3.52–3.79 degrees at the calf and 5.88–5.96 at the thigh.
None of these six candidates introduces an extra full turn relative to MotionIR.
Bounded differences are reported without assuming they are defects: contact
correction may intentionally modify local angles.

Reports: `../tmp/m4-motion-center/rotation-transfer-walking-v1/` and
`../tmp/m4-motion-center/rotation-transfer-turn-v1/`. Four additional tests cover
preserved two-turn motion, an introduced turn that modulo would conceal, bounded
correction and mismatched source/target durations. Target appearance and the cause
of source-projection singularities still require the planned visual adaptation.
