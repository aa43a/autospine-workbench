# Bounded torso projection experiment

`source-torso-plane-shape-v1-experiment` observes the two shoulder joints and
pelvis in the verified BVH or SOMA77 source and declared projection view. It
removes the torso axis roll already represented by MotionIR, then measures
longitudinal scale, signed transverse scale and local shear relative to the
source setup frame. It models a plane, not an observed body surface.

The experimental bounds are transverse 0.5–1.5, longitudinal 0.75–1.25,
absolute shear at most 0.5 and projected shoulder visibility at least 0.2.
Unsupported selected frames remain in the report and block the candidate;
the algorithm does not clamp them or drop time intervals. A back-facing plane
requires different artwork. These bounds limit experiments, not prove quality.

`torso-plane-compensated-deform-v1-experiment` applies the shape to the canonical
chest hierarchy. Shoulder origins move with the torso; neck and upper-arm world
linear transforms are preserved to avoid compressing the head or arm textures.
Existing deform offsets are composed before baking the new weighted-mesh keys.
Setup bones, weights, UVs, triangles, textures and draw order remain unchanged.
This is an animation-specific visual bake: editor bone guides remain at their
original animated positions. It is not yet a default workbench strategy.

Run from the repository:

```powershell
$env:PYTHONPATH='src;tools'
python -X utf8 tools/m4_torso_projection_candidate.py EXACT_MOTION_JOB OUTPUT --capture
python -X utf8 tools/review-torso-projection.py OUTPUT
```

The tool checks the exact source/character identities and stored MotionIR before
building an isolated candidate. It creates new geometry references and official
Runtime captures; it does not reuse old geometry conclusions or submit a review.
Contact and depth remain explicitly unmeasured for the changed candidate.

## Actual evidence

Hongmeiling's -30° raise source candidate
`motion-71e9441a4dbc41f6b4734e01228e2919` generated an isolated candidate at
`../tmp/m4-motion-center/torso-projection-hong-raise-v1/`.
The candidate passed geometry and 633 fresh official Runtime frames, with maximum
reference error 0.000117446 px. Maximum influence displacement was 31.2901 px.
The draggable `review.html` uses hash-verified actual capture PNGs and clip times.
Neither contact/depth nor visual acceptance has been inferred from this result.

Full turning candidate `motion-4de7a1c108384e12a513621a7f5c119a` retained 31
unsupported source frames and produced no replacement skeleton. At 0.433333 s,
the transverse ratio reaches 0.4506; at 0.5 s the shoulder projection is near
degenerate. Evidence: `../tmp/m4-motion-center/torso-projection-hong-turn-v1/`.
The real Kimodo wave source was also extracted: 120 frames, none outside these
source shape bounds. That extraction alone is not target or Runtime validation.

Twelve core and affine regression tests pass. They cover shoulder narrowing,
roll isolation, side/back rejection, preserved arm/head shape, unaffected legs,
input preservation and composition with an existing deform.

## Fresh checks and workbench strategy

`torso_projection_validation.py` proves that the setup and non-deform animation
are unchanged, then samples actual foot-weighted vertices. This distinguishes
unchanged ankle bone paths from a deform that can still move the foot surface.
Missing foot evidence remains unmeasured; floor and sole contact are not inferred.
For the isolated Hong candidate all 633 sampled foot paths were preserved.

The coarse source-depth/actual-alpha check was rerun on the new mesh: 179 visible
pair samples, 32 ambiguous samples, no unmeasured pair samples, 28 straddle order
failures and four unmapped-order conflicts. Local depth models anchored to the
old bone guides are not reused. Counts from different depth profiles must not be
treated as an improvement/regression comparison.

Workbench target controls now expose “躯干投影偏斜（实验）”, disabled by default.
FBX/BVH and Kimodo NPZ are supported by source extraction. It creates an exact
new candidate; retry retains the explicit strategy and source changes reset the
checkbox. It currently requires the standard overlap depth strategy, because
regional depth refinement still uses unwarped bone guides. Conflicting choices
are rejected rather than silently changed.

The worker applies the bake after existing contact correction, checks foot
preservation, then regenerates overlap, geometry, Runtime and candidate evidence.
Unsupported source frames preserve a diagnostic original and add a projection
exception. A failed foot-preservation check cannot inherit a contact pass.
The readiness panel includes a candidate-bound torso stage, and view comparison
does not mix torso-enabled candidates with historical strategies.

The real API task `motion-de081c9760914eb4b83c7595ae28223a` completed on
Hongmeiling's -30° raise motion. Exact artifact:
`cf4e0b865dda7da5922223c2b962c57499c5b01b03593b3e2f15effff78a3b33`.
Its new geometry and 646 Runtime frames pass; foot paths are preserved, with
inferred ankle correction retained. Depth still requires review and aggregate
readiness is `needs_changes`. This is not visual acceptance.

The downloadable ZIP was read back and all 93 entries compared byte-for-byte
with the addressed store artifact (72,016,688 bytes in the ZIP). Live Chrome
checks verified strategy selection/reset/conflict handling and the new task's
readiness/inline view comparison. Its comparison includes only itself and makes
no recommendation. Policy, worker integration, identity, retry and contact tests
passed; progress transport explicitly includes the torso stage.
