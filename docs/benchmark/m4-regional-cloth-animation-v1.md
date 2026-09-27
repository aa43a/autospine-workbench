# Regional cloth animation diagnostic

This experiment uses the existing isolated Alice Squat −55° branch, not the
frontal fixed-cohort candidate. It is not selected or visually accepted.

Source bundle: `1d72f0c17f53b1c33f9a7ac5f9a6634e7fdbfe198b7883a435d78f75856a2780`.
The input is `tmp/m4-moving-workbench/alice-squat-regional-cloth-v7`.
All four corrected poses are retained, including the failed 0.9-second pose.

`regional_pose_bake.bake` transforms world-space corrective displacements into
weighted-bone local offsets and adds them to the original linear deform curve.
It preserves source breakpoints, skeleton topology, UVs, bone animation and other
attachments. Added times avoid Float32 aliases. The diagnostic correction fades
from zero at 0.7 seconds and returns to zero at 1.1 seconds; this fade is an
experimental interpolation choice, not an accepted motion design.

The interpolation tool checks 635 times: original and added interval knots,
their midpoints, original pose times, and a 240 Hz grid. It checks all 25 retained
covered material samples, skirt geometry, the 8-pixel displacement budget and
17 waist material anchors. Samples are not dropped to improve the result.

Output: `tmp/m4-moving-workbench/alice-squat-regional-animation-v1/`, containing
`skeleton.json` and `report.json`. The report preserves input hashes and failed
keypose statuses. It does not inherit parent Runtime or visual acceptance.

Measured result: 254/635 sampled times fail material coverage, with first/last
failures at 0.7428386807441711 / 1.0408855676651 seconds. No sampled skirt geometry
failures occurred. Maximum corrective displacement is 7.9999999200540595 pixels;
maximum waist-anchor movement is zero. These counts are temporal diagnostic
samples, not independent statistical observations or a whole-character error rate.

Baked skeleton SHA-256:
`fd645410983d1447c5adc577049128494d7c62024986e5cc7b828dc5325bf915`.
The full source/reference/key/midpoint union requires 6,975 Runtime times, above
the single-capture limit. It must be batched without dropping source samples if
this diagnostic proceeds to official Runtime; no such capture is claimed here.

The next repair target is continuous material coverage across this interval.
Increasing vertex displacement or hiding failed samples is not justified by
the keypose results. The current candidate remains unselected.

Full-character geometry, official Runtime, continuous visible-lower-leg guards
and framebuffer/visual review remain separate checks. In particular, successful
keypose fitting does not prove interpolation quality or resolve missing 3D depth.
