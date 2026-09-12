# Residual texture transfer trial

This trial transfers only alpha 1–7 pixels to a unique same-source weighted mesh. Destination texture dimensions and every mesh UV/setup position must align with the residual quad. A single mesh triangle must contain all four texel corners. Existing destination alpha, unsupported UVs, incomplete texel coverage and geometry outside the mesh leave the source pixel untouched.

The transferred RGBA bytes are copied exactly and only their source alpha is cleared. Skeleton, bone weights, animation keys, numeric references and atlas layout remain byte-identical. Matching editor image aliases are updated; mismatched aliases fail. New texture inventories receive independent trial bundle identities. Binding and region decisions, workbench registration and layer completion states are unchanged.

| Character | Transferred | Retained | Trial bundle |
| --- | ---: | ---: | --- |
| Huiye | 1,006 | 100 | `7d6c2f7dbe5a6edbc65b7de7001f9d8b241a89f388948a99ee584d58656f993e` |
| Xiaoemo | 754 | 132 | `5494a9eae7b973730d37608da6592fe1d9f929f42a5ee1757028f7a288593fc6` |

Official `@esotericsoftware/spine-webgl` 4.3.13 captured all existing animation reference frames: Huiye 2,062 frames / 25 slots, Xiaoemo 1,675 frames / 31 slots, both passed. Target remains Spine 4.3.26. Captures are under `../tmp/character-residual-transfer-runtime/{huiye,xiaoemo}`.

The comparison tool verifies report renderer context, identical skeleton/atlas/references and screenshot hashes before comparing matched animation/index pairs. Huiye has 27 matched screenshots; Xiaoemo has 21. Every captured initial frame is byte-identical. Across moving frames the largest alpha difference is 7/255. Maximum composited channel difference is Huiye 4/255 on black and 5/255 on white; Xiaoemo 5/255 on either. Raw transparent RGB differences can reach 255 and are not treated as visible contrast.

These differences are measured, not an established visual acceptance threshold. Huiye's pre-existing upward drape shape remains visible in wave-left frame 256. This trial does not repair that shape, certify all continuous raster times, or authorize adopting residual ownership. Remaining pixels stay explicit, and existing whole-character blockers remain.

Seven tests/checks cover exact texel composite preservation, source immutability, collision/UV rejection, setup coordinate invariance, replay texture stability and file budgets. The next integration needs an explicit candidate review/undo path and a decision on pixel footprints spanning adjacent triangles; do not delete those pixels merely to clear a ledger row.
