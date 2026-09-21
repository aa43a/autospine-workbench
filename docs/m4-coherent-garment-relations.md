# M4 garment relations in coherent region ordering

The same-frame cycle probe identified an arm/skirt edge that still used setup
order while the arm/chest edge used source-derived proxy depth. This slice reuses
the existing explicit torso-anchored garment plane for that missing relation;
it does not introduce measured cloth depth or a new production default.

`m4_supplement_garment_trace.py` verifies the frozen source/observation pair,
source job, motion bundle and reconstructed MotionIR. It retains every original
trace row and appends checks for explicitly selected garment slots. Each arm
is sampled once per unique source-frame or midpoint time. Ambiguous checks stay
ambiguous; failed checks discard partial triangle accumulations and remain
unmeasured. Existing warped-torso and Kimodo inputs are explicitly outside this
particular BVH experiment, rather than silently using incompatible coordinates.

The model assumes the garment stays in the torso plane, without thickness or
out-of-plane cloth motion. Its coefficients are fitted from the existing target
shoulder/pelvis anchors and normalized source depths. The garment's actual
deformed alpha footprint participates in overlap sampling, but its auxiliary
bones do not supply observed Z. That limitation remains attached to the trace
and the downstream coherent-order report.

The coherent builder now accepts opt-in shared-boundary refinement and records
its parent report hash and supplemental model assumptions. No other default
inference, quality margin, cycle limit or adoption behavior changes.

## Complete turning clips on two structures

Each character contributes 44 source frames plus 43 midpoints, two arms against
`layer-005`: 174 added checks per character. Slot selection is an explicit
experiment argument, not a character-name heuristic.

| Added relation checks | Alice | Hongmeiling |
| --- | ---: | ---: |
| No alpha overlap | 46 | 51 |
| Uniform arm in front of plane | 9 | 7 |
| Uniform arm behind plane | 55 | 103 |
| Mixed or insufficient depth | 64 | 13 |
| Unmeasured | 0 | 0 |
| Raster budget consumed | 11,250,596 | 10,459,242 |

Both runs preserve source geometry at all 87 sampled times and violate zero
hard front/back proxy labels. Whole-order results remain blocked:

| Whole-order result | Alice | Hongmeiling |
| --- | ---: | ---: |
| Regions | 245 | 291 |
| Visible ordering conflict times | 35 | 12 |
| Visible mixed-depth failure times | 7 | 11 |
| Cycle-check limit times | 1 | 0 |

Previously the respective counts were 54/2/1 and 2/11/0. These are first-failure
diagnostics from different constraint inventories, not directly comparable
visual error rates. More constraints can expose other previously unseen cycles.
No replacement skeleton or new Runtime capture was produced.

At Hongmeiling 0.433333s, original source triangles 254 and 255 have 49 and 83
skirt-overlap samples supporting arm-in-front; triangles 256 and 257 have no
skirt overlap. At 0.45s, triangle 240 has 72 such samples. This supplies a
conditional model for the old missing edge, but those times still fail whole
ordering due to another skirt layer (`layer-002`). Other newly exposed cycles
involve the leg (`layer-003`). Therefore this is not a claim that the two frames
are repaired. Additional per-body inference also still leaves arm/skirt/chest
cycles later in the motion.

## Evidence and next step

The [frozen audit](benchmark/m4-garment-trace-evidence-v1.json) verifies the original
rows are unchanged and binds checks, merged observations, assumptions, inference
and order reports by hash. Local folders:

- `../tmp/m4-motion-center/garment-trace-{alice,hong}-v1/`
- `../tmp/m4-motion-center/coherent-garment-{alice,hong}-v1/`

Unit coverage includes time deduplication across bodies, source-time conflicts,
duplicate pair rejection, original-row preservation and partial-failure handling,
alongside the existing plane, interval, inference and boundary tests.

Next work must use a complete inventory of intersecting anatomical and garment
surfaces and reconcile their constraints together. Independently adding one
garment pair does not establish a consistent surface order. Garment proxy
assumptions and missing depth must remain visible through any joint solution,
and a new candidate still needs continuity checks and fresh Runtime rendering.
