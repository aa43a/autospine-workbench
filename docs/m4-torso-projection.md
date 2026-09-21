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
input preservation and composition with an existing deform. New full-character
contact/depth checks and workbench strategy integration remain required.
