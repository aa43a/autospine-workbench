# Boxing forearm: surface hypothesis and interpolation repair

2026-09-28. All results are isolated experiments; no adoption or human review changed.

## Exact parent

Hongmeiling boxing job `motion-6c01b6ac334947729089deabcb1dbed5`, artifact `d6be67d4a04c3c01d661ac81ad8c06037fe1539090859884776bf5b5aa720767`, right-arm attachment `layer-001`. The original 321-sample Runtime geometry report has six failing right-arm samples, two with inversions; first failure is at 0.38671875 seconds. Other attachments pass that existing report.

## Surface test rejected

`tools/m4_arm_surface_probe.py` reuses the existing cylindrical-front-surface proxy, adding only its weighted forearm displacement to the exact parent pose. Both front-sign hypotheses retain source identity and radius evidence. The report is `E:/proj/unusual/localset/tmp/m4-boxing-source-v1/forearm-surface.json`.

All 67 original source keys pass the sampled right-arm area/edge checks. Both curved-surface signs introduce new area failures at all 67 keys, with maximum offsets about 86.90 and 86.21 px. These are failed hypotheses, not substitute candidates; no Runtime capture or visual acceptance is requested. The chosen cross-section/radius is not recovered anatomy.

## Existing deformation retained, intervals repaired independently

The key-versus-interval distinction changes the next action: first repair the existing interpolation failure rather than replace the entire arm representation. `tools/m4_additive_interval_repair.py` keeps every existing numeric-reference time and original key, adds bounded local corrections to the original deform, and verifies that only the selected attachment deform can differ. Bones, weights, UVs, textures and other attachments remain unchanged. New midpoint failures drive bounded refinement.

At the original sampled failure near 0.386719 seconds, local correction raises the minimum area ratio from about 0.4425 to 0.55 with 0.85 px maximum displacement and zero fixed-vertex displacement. This local result is insufficient to prove a continuous animation.

The actual bake is `E:/proj/unusual/localset/tmp/m4-boxing-interval-repair-v1/`. Four rounds grow from 321 to 330 correction knots, checked at 659 union/midpoint times. Nineteen knots receive corrections, maximum displacement 10.6294 px. Three inversions persist:

| Time | Minimum area ratio |
|---:|---:|
| 0.407666015625 | −0.050635 |
| 0.541943359375 | −0.121147 |
| 0.592431640625 | −0.038708 |

The isolated candidate is therefore not adopted. No new whole-character Runtime, contact, depth or visual pass is claimed. Source projection and prior contact/depth exceptions remain independent unresolved evidence even if interpolation later improves.

## Validation and next action

Eight existing surface-proxy and parent-pose-repair tests pass. The real-data experiments above are the validation of the new probe tools. These are diagnostic tools, not enabled default production policies.

Next investigate temporal consistency of the local solver and inverse-transform/deform interpolation around the three persistent intervals. Further refinement must retain all parent samples and prove that it avoids new failures, rather than reporting only repaired knots.
