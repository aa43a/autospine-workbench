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
The selected source batch/reference/key/midpoint union contains 6,975 times.
This is not the complete parent validation grid: the parent report contains
14,928 times. Their complete union is 17,452 times. The Runtime runner retains
all of them using 19 batches of at most 1,024 times, including each batch's
time-zero reference. No source sample is discarded and no capture limit is
increased. See `tools/m4_regional_cloth_runtime.py`; a running job is not proof
of capture success.

The next repair target is continuous material coverage across this interval.
Increasing vertex displacement or hiding failed samples is not justified by
the keypose results. The current candidate remains unselected.

Full-character geometry, official Runtime, continuous visible-lower-leg guards
and framebuffer/visual review remain separate checks. In particular, successful
keypose fitting does not prove interpolation quality or resolve missing 3D depth.

## Continuous regression check

`tools/m4_regional_cloth_regression.py` independently compares source and baked
curves at all 635 saved times. Batched bilinear sampling matches the existing
scalar sampler in tests covering edge clamping, reversed winding, overlapping
triangles and degenerate geometry. Real-candidate failure membership must also
match the previously saved scalar results exactly; mismatches stop the report.

`regression.json` in the same output directory records:

- Newly uncovered material: zero sampled times.
- Restored coverage: 5,295 sample-time pairs (not unique points or pixels).
- Existing gaps still uncovered: 254 sampled times.
- The one previously visible lower-leg material anchor: zero guard failures over
  635 times. This is a single-point protection result, not whole-leg coverage.

The source candidate, skeleton and evidence hashes are retained. The continuous
single-point guard is now measured; complete limb occlusion, official Runtime
and visual review remain pending. No acceptance or default selection changed.

`tools/m4_regional_cloth_runtime_audit.py` checks the actual stored files against
the source and experimental skeleton: exact numeric-reference times, render
identity, saved geometry, and official Runtime results. `--partial` audits only
completed batch records during a live run and explicitly returns `complete:false`;
it cannot declare full coverage until all 19 batches and the final summary agree.

`tools/m4_regional_cloth_player.py` requires that complete audit before creating
the diagnostic entry page. It checks the exported scene's candidate and skeleton
identity, unions all batch viewports, and retains the unselected status and
material failures beside the motion/time controls. Tests cover refusing incomplete
captures and retaining the full viewport and failure label. Actual export remains
dependent on the running capture completing; these tests are not browser evidence.

## Captured-frame observation during the live run

The assistant inspected `batch-008/runtime/frames/external-motion-320.png` at
0.8998535051941872 seconds and the same batch's `setup-frame.png` directly.
The animated image SHA-256 is
`7cc49900b841ac539ba05b569c91bd5ae642bd7ac178ea199030109ce3c667f6`;
its batch bundle is
`790c2e6582789fc0d24802c860b5caf408dac4b82731f73df58f055315a6aef0`.
That frame's numeric maximum error is 0.0000762704912902971 pixels, with zero
border pixels and matching draw order. These are rendering checks, not visual
quality acceptance.

Both setup and animated images contain conspicuous scattered transparent-edge
pixels around the head/shoulders. They are not established as a new cloth-repair
regression. The animated torso is strongly slanted while the head artwork remains
frontal, and the skirt conceals most of the bent-leg shape. The isolated −55°
projection therefore still needs whole-character appearance review. No conclusion
about the remaining microscopic coverage samples can be drawn from this full-view
image, and no user acceptance is recorded by this observation.

## Completed Runtime capture

All 19 batches completed against the same baked skeleton and texture inputs.
They cover 17,452 unique times (17,470 evaluations including repeated setup
anchors). Full-character sampled geometry passed in every batch. Official
Runtime numerical comparison passed, with maximum error
0.00008301345142698096 pixels. The installed official renderer reports version
4.3.13; the export target remains Spine 4.3.26. These version identities are not
interchangeable and are retained in each capture report.

The output directory is `tmp/m4-moving-workbench/alice-squat-regional-runtime-v1`.
The live player's exact skeleton is shared by all batches; its final diagnostic
entry is generated only after the stored-file audit and viewport union. The
existing 254 material-coverage failure times remain unresolved. Numerical and
geometry success do not grant visual acceptance or default adoption.

## Exact-time framebuffer classification

`tools/m4_cloth_capture_coverage.py` joins failed material samples only to an
existing screenshot at exactly the same time, verifying capture and image hashes.
The current captures cover 10 of the 254 failed times exactly; 244 remain without
an exact screenshot. All ten matched screen pixels have alpha 255. They are not
transparent framebuffer cracks. This does not prove garment coverage: an opaque
leg can be visible through a garment coverage failure.

At 0.7705731391906738 seconds, batch-006 frame 256, pixel (479, 853), the captured
RGBA is (193, 185, 207, 255). Independent pixel provenance finds left-leg
`layer-001-l` alpha 255 and skirt `layer-005` alpha 2.4779739845672157 at the pixel
center. The original subpixel material query reports cloth alpha zero; these are
different sampling locations, not contradictory measurements. This supports an
exposed-leg/garment-occlusion classification for this point, not a transparency
repair. Whole-view observation shows a pale leg area protruding beside the skirt.

The exact-time report and unmodified-image magnifier are in
`tmp/m4-moving-workbench/alice-squat-regional-framebuffer-v2/index.html`.
The independent pixel trace remains in
`tmp/m4-moving-workbench/alice-squat-regional-framebuffer-v1/pixel-trace.json`.
No neighboring-time screenshot is substituted, no missing frame is counted as
passed, and no raster edits or acceptance changes are made.
