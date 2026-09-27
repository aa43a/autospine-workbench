# Squat source view and knee readability

The existing source-view scan now includes 3D versus 2D knee-bend loss over both
legs and every source frame. No source samples, clip range or character decisions
are changed. It retains torso projection checks and limb-collapse evidence instead
of choosing a camera from knee readability alone.

Actual request: `motion-8a48f34642c643e397f95b433046b8bb`.
Output: `tmp/m4-moving-workbench/squat-view-knee-scan-v2.json` and `.html`.
The report retains the verified source identity, request and vector hashes.
The complete 57-frame source contributes 114 leg samples at each of 37 views.

| Yaw | Maximum hidden bend | Samples losing ≥30° | Source torso check |
| --- | ---: | ---: | --- |
| −90° | 2.51° | 0 | unsupported |
| −55° | 26.30° | 0 | passes |
| −45° | 41.17° | 24 | passes |
| −30° | 76.64° | 39 | passes |
| 0° | 63.06° | 80 | passes |
| +30° | 102.43° | 37 | passes |
| +55° | 31.54° | 4 | unsupported |
| +90° | 2.51° | 0 | unsupported |

The 30° count is diagnostic, not an adoption threshold. The −55° source torso
pass does not contradict the observed character appearance and garment occlusion
failures: these are different requirements. A smaller yaw is not monotonically
better for knee bend. Side views preserve bend but cannot establish compatibility
with frontal artwork. Do not automatically promote any row based on this scan.

The local cloth-repair budget counterexample remains attached to its exact −55°
candidate. Further development needs a coherent pose/view representation rather
than repeatedly optimizing that candidate's few material anchors. New target
geometry, contact, occlusion and visual checks remain required for any alternative.
