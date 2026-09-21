# M4 same-frame cycle localization

Ordering cycles may result from overlaps at different positions, overlaps at
different held-order sample times, or mutually incompatible requirements at
the same pixel. Subdividing attachments may help the first case; it cannot
satisfy a directed cycle whose surfaces all overlap at the same location without
reconsidering at least one ordering requirement. None of these categories proves
which surface-depth inference is physically correct.

`depth_cycle_pixels` validates a simple cycle and samples the exact compact
candidate at the failure time and each recorded edge-witness time. It applies
the existing native-pixel bilinear alpha>=8 convention to every participating
attachment in one common ROI. It records every adjacent pair's overlap, the
intersection of all participating masks, world-space pixel-center examples and
the common raster bounding box. World Y is inverted only for raster coordinates.

It distinguishes simultaneous support, spatially distributed support, absent
simultaneous edge support at the selected time, and unmeasured resource limits.
The scope is the reported simple witness, not exhaustive pixel-cycle search or
continuous-time proof. Original depth labels and all source/candidate artifacts
remain unchanged. The raster includes edges and is not a replacement for GPU
fill-rule, blending or official Runtime validation.

## Actual fixed-source results

| Character | Sampled witness/time rows | Same-pixel cyclic support | Other sample times |
| --- | ---: | ---: | ---: |
| Alice | 61 | 54 | 7 without simultaneous cycle support |
| Hongmeiling | 2 | 2 | 0 |

The 54 Alice rows correspond to all 54 visible ordering failure times. Seven
extra rows inspect edge-witness times; they do not cancel the recorded failures.
One cycle-check resource failure and two mixed-depth failures were outside this
simple-cycle probe. Hongmeiling's eleven mixed-depth failures also remain.

Hongmeiling has 33 common pixels at 0.433333s and one at 0.45s. The first cycle is
`layer-005 → layer-009 → layer-001-depth-027 → layer-005`. At that first time,
all four source triangles 254–257 in the arm region have original `F` proxy
labels against layer-009, not newly inferred ambiguous labels. Source triangle
240 in the second region likewise has `F`. The body/body and arm/layer-005 edges
come from preserved visible setup order. This identifies a missing arm/garment
relationship, rather than a problem solvable solely by smoothing arm labels.
It does not authorize replacing that missing relationship with an assumed Z.

## Review and provenance

`tools/m4_cycle_pixel_probe.py` verifies the frozen order-report, parent-report,
compact-skeleton and source artifact identities. It generates alpha-support
heatmaps and enlarged common-overlap crops. The review page lets users select or
scrub sampled exception times, showing each edge's evidence source. Colored
regions are diagnostic masks, not the character's rendered colors. White marks
common coverage; the original numerical report is linked.

Outputs: `../tmp/m4-motion-center/cycle-pixels-{alice,hong}-v1/`.
[Frozen audit](benchmark/m4-cycle-pixels-evidence-v1.json) includes report and
heatmap SHA256 values. No replacement candidate or Runtime capture was generated.
Unit tests distinguish pairwise-only overlap from common overlap, alpha absence,
world/raster mapping, immutable input, invalid cycles and budget abstention.
Chrome checks verified image loading, color legend, time scrubbing and selection.

Next, the ordering solver needs explicit evidence or a separately declared
visual-adaptation model for arm/skirt relations. Simply subdividing the same
conflicting requirements or increasing the cycle-check limit cannot settle
the demonstrated simultaneous conflicts.

The next [garment-relation experiment](m4-coherent-garment-relations.md) reuses
the existing explicit garment-plane model and preserves these limitations.
