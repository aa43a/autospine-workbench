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
