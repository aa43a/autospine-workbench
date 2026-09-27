# Side walking: bounded ankle failure diagnosis

2026-09-27. Candidate `motion-06ec02183a644786a2ac435633d572ce`, artifact
`c535f0ce650a4d9eafa7bcb82e06bedb4a37850f67466789b5825870724435f1`.

The build completed, but moving-ankle correction was not applied. The retained
animation passed 753 Runtime geometry samples; this does not validate the failed
correction. Contact and depth exceptions remain.

The first solver failure is at 0.063020828125 seconds. The endpoint threshold is
5.493700613 px; errors are 6.168450439 and 6.284324251 px. The previous solution
at 0.04726562109375 seconds has right calf correction +1.764441488 degrees.

`tools/m4_moving_ankle_failure_probe.py` verifies the exact original skeleton
identity before comparing three solves against the same target points:

| Constraints | Maximum endpoint error | Result |
| --- | ---: | --- |
| Original root and correction angular speed limits | 6.284324251 px | No bounded solution found |
| Root continuity, no angular speed constraint | 0.000017043 px | Single-frame candidate |
| Independent frame, same spatial bounds | 0.000018150 px | Single-frame candidate |

The root-continuous alternative uses right calf correction +24.566851791 degrees,
over 22 degrees from the previous solution within 0.015755207 seconds. It must
not be adopted as a timeline: removing the speed bound would introduce a jump.
This demonstrates spatial reachability at this frame, not feasibility of the
whole motion under continuity limits or proof of global infeasibility.

Next implementation direction: solve a temporal window with alternative knee
branches and unchanged endpoint, root displacement, angular displacement and
continuity checks. A local greedy trajectory can select a branch that cannot
continue. Determine whether a continuous bounded path exists before changing
any limits. Keep failed inputs and never publish a partial corrected animation.

Receipt: `E:/proj/unusual/localset/tmp/m4-walking-ankle-failure-probe-v1.json`.
No candidate, source animation, production threshold, or human decision was
modified by the probe.

## Joint window experiment

`ankle_window_solver.py` jointly searches the first six knots, trying neutral
and opposite knee seeds. The initial correction remains zero. Root displacement
15%, correction rotation 30 degrees, root speed 2 reference lengths/second,
correction angular speed 180 degrees/second, and endpoint error 1% stay unchanged.
The optimizer uses numerical headroom and independent post-solve inequalities.

The real source now admits a knot-level path with peak endpoint error
5.488179345 px. Reconstructing the animation and checking full affine FK at
knots and midpoints (11 times) finds 5.591680460 px at 0.055143224609375 seconds,
right foot, above 5.493700613 px. This path is therefore **not adopted**.
The next step must constrain interpolation samples, then extend beyond this
initial window; the short window is not evidence of whole-walk support.

Receipt: `E:/proj/unusual/localset/tmp/m4-walking-ankle-window-probe-v1.json`.
19 focused tests pass, including independent FK, continuity bounds, immutable
inputs, invalid windows and unreachable-window rejection. No production route
uses the experimental solver yet.

## Interpolation-constrained window

Version 2 constrains quarter-interval samples using actual animated affine
transforms and linearly interpolated correction parameters. It rejects omitted
source animation knots instead of silently changing the original base timeline.
An independent reconstruction checks eighth-interval samples.

The original six-knot window now passes 41 FK samples: worst error
5.493645678 px, below 5.493700613 px. This is a very small margin and sampled
evidence only. Receipt: `../tmp/m4-walking-ankle-window-probe-v2.json` relative
to the repository root.

Extending to 0.15 seconds using all source and target knots still finds no
bounded path in three seeds; the best trial has 8.075080047 px error and fails
root displacement, root speed and endpoint checks. No infeasibility proof is
claimed. Receipt: `../tmp/m4-walking-ankle-window-015-v1.json`. This longer
experiment must not inherit the short-window pass. Next inspect source body
translation versus target ankle displacement before expanding root limits.

## Coordinate and ancestor-channel probe

`tools/m4_ankle_coordinate_probe.py` checks the unchanged input skeleton hash,
then compares its root translation with the MotionIR translation scaled by
549.370061307 px and with the declared Y inversion. The maximum discrepancy
over the union of translation knots is exactly 0 px. This verifies adapter
translation consistency; it does not prove the upstream source map is correct.

At 0.15 seconds, original foot errors are 78.136976 / 72.085762 px. Removing
only animated root rotation in a read-only counterfactual reduces them to
60.946669 / 54.545176 px, but they remain far above the gate. Root rotation alone
is therefore insufficient as an explanation or repair. Its effect on hip
position is approximately -68.379 / -70.157 px in X. The target root is at
(663.4, -1261.7), below the pelvis; source root orientation and target rotation
center require further analysis. Removing rotation is not an adopted remedy.

Receipt: `E:/proj/unusual/localset/tmp/m4-walking-coordinate-probe-v1.json`.
The next experiment should preserve source orientation while comparing
pelvis-centered versus target-root-centered rotation, and independently check
leg setup-axis mapping. Do not enlarge the local correction budget to conceal
an upstream representation mismatch.

## Pelvis-centered rotation candidate

`root_pivot_candidate.build` preserves source root rotation and all non-root
channels, adding only the root translation needed to keep the direct-child
pelvis on its unrotated trajectory. It preserves initial animated orientation,
requires original root knots, and reports interpolation error. It does not
overwrite the original candidate or claim contact acceptance.

Full walking comparison (485 times, both feet):

| Measure | Original | Pelvis pivot |
| --- | ---: | ---: |
| Ankle RMS error | 96.791360 px | 86.592139 px |
| Worst ankle error | 222.010892 px | 210.247976 px |

The pivot candidate uses at most 64.888687 px root compensation. Its pivot
interpolation residual is 0.015775 px. The remaining foot error is far above
the 5.493701 px tracking gate, so the candidate is not adopted. Next investigate
source setup-axis mapping and source/target leg shape, not just root origin.

Artifacts: `E:/proj/unusual/localset/tmp/m4-walking-pelvis-pivot-v1/`.
Skeleton SHA256 `37cafd0f16ea73940fcb5d4f929b45d7e89ead0f125d46f3f2f837506af3e3de`.
The test checks retained source orientation, moving pelvis target, interpolation
and input immutability. No Runtime or mesh claim is made for this experiment.

## Absolute leg-direction comparison

The verified side source starts its right upper leg at -133.586 degrees in
Spine screen coordinates; the target begins at -93.450 degrees. Relative angle
retargeting retains this roughly 40-degree offset. Source ankle displacement
and target initial leg pose are therefore not interchangeable constraints.

`tools/m4_walking_pose_probe.py` reuses the existing absolute limb-direction fit
for legs only, preserving existing animated axial scales and upper-body motion.
Each variant measures source displacement relative to **its own** initial feet;
the initial pose changes are explicitly recorded, not hidden as accuracy gains.

| Variant, 485 times | Ankle RMS | Peak |
| --- | ---: | ---: |
| Original | 96.791360 px | 222.010892 px |
| Absolute leg axes | 55.900780 px | 120.419518 px |
| Absolute leg axes + pelvis pivot | 38.486901 px | 82.637761 px |

The combined result still fails the 5.493701 px tracking gate and has not been
adopted. It changes both initial foot positions substantially; geometry,
silhouette, contact and Runtime must be checked before any future adoption.
Next separate the inherited relative length scaling from absolute source
projection and character leg proportions, then retry bounded contact solving.

Exact-source artifacts: `E:/proj/unusual/localset/tmp/m4-walking-absolute-legs-v1/`.

## Full calibrated ankle solve and geometry

Absolute projection-length replacement alone increases RMS error to 46.823739 px
(with pelvis pivot), versus 38.486901 px with retained relative scales. The
experiment explicitly records the replaced four scale channels; it is not a
silent change to the source or accepted output.

After calibration, the existing bounded moving-ankle solver completes all 243
knots for both policies. Independent FK at 485 times gives:

| Policy | Worst ankle error | Additional root shift | Geometry |
| --- | ---: | ---: | --- |
| Absolute axes + pelvis pivot | 0.265164 px | 55.827664 px | layer-003 fails |
| Absolute projection + pelvis pivot | 0.193169 px | 62.549321 px | layer-003 fails |

Both track the source ankle displacement below 5.493701 px. This is not evidence
of stationary shoe-floor contact. Geometry uses the original rig setup vertices,
not the changed frame-zero pose. The failed layer has no inversions but minimum
triangle area ratios 0.334539 / 0.347444, below 0.5. The first failures occur at
0.70833325 / 0.67500025 seconds; 79 / 88 sampled frames fail, respectively.
These candidates are **not adopted** and have not undergone new official Runtime
capture. All other sampled slot records pass this geometry check.

Reproducible command: `tools/m4_walking_refit_contact_probe.py` takes the
calibration output directory and a new output directory. It checks input
skeleton identities and preserves failed geometry reports. Artifacts are in
`E:/proj/unusual/localset/tmp/m4-walking-calibrated-contact-v1/`.
Next locate the failed triangles and classify projection compression versus
material strain before choosing a local repair or representation limitation.
