# Shared-plane ambiguous depth inference

This isolated experiment addresses contradictory inferred front/back labels for
the same arm triangle against different surfaces using the **exact same** torso
plane model. It does not synthesize side/back artwork or change a production rig.

The complete surface inventory exposed two different failure mechanisms:

* Hongmeiling has six order-conflict times from 0.566667s to 0.65s where the
  implicated triangle is ambiguous against both reference surfaces, yet the
  independently inferred labels disagree.
* Other conflicts involve a source sample with no overlap followed by an
  overlapping interval sample. Agreement at the source sample cannot establish
  the correct ordering for that later overlap.

## Algorithm and limits

`depth_plane_coupling.py` groups evidence only when arm, time, source tick,
plane coefficients and the complete plane evidence (including anchors) agree.
For each group, only corresponding **A / A** triangle labels receive a soft
disagreement cost of 8. Existing adjacency costs remain 8 and previous-label
costs remain 1. F/B hard observations, unknown/mixed states and no-overlap
labels remain fixed. Different reference planes are never merged.

The bounded binary solver retains its existing 4,096-node and 16,384-edge
limits. These cost values are experimental regularization choices, not
calibrated confidence or measured garment depth. Soft coupling can still leave
a disagreement when other evidence outweighs it. No shared-plane assumption
is applied to unmodeled hair or objects.

The original states and independent labels remain in the output. An independent
audit compares before/after inventories and source identities, rejects any
non-A change, and separately recomputes between-sample transitions. Full
source/midpoint geometry correspondence and the existing strict draw-order
checks still run. Any remaining conflict prevents skeleton emission.

## Reproduction

With `PYTHONPATH=src;tools`, run `tools/m4_coherent_region_order.py TRACE OUTPUT
--surface-routing --shared-boundaries --shared-planes` using a new output
directory. `TRACE` must contain the complete surface report, observations and
hash-verified checks. Compare independent/coupled output pairs with
`tools/m4_plane_coupling_audit.py OUTPUT_JSON BEFORE AFTER [BEFORE AFTER ...]`.

This is a CPU inference/order experiment. A successful order result would still
require official Runtime rendering and visual inspection before adoption.

## Frozen turning-clip comparison

Both characters retain all 87 source/midpoint geometry checks. Against the
independent complete-surface run:

| Result | Alice | Hongmeiling |
| --- | ---: | ---: |
| Visible ordering conflicts, before → after | 35 → 6 | 11 → 8 |
| Remaining depth-straddle failures | 7 | 11 |
| Remaining cycle-check limit failures | 1 | 0 |
| Changed ambiguous labels | 242 | 196 |
| Modified non-ambiguous labels | 0 | 0 |

These are diagnostic counts, not a visual defect rate. Both complete clips remain
blocked, emit no replacement skeleton, and have no new Runtime capture. The
observations, textures, weights and vertex geometry are unchanged. The next
issue is interval-local overlap/depth evidence; stronger soft costs alone cannot
establish a missing measurement or resolve a triangle spanning both depths.

The [frozen audit](benchmark/m4-shared-plane-evidence-v1.json) records exact
before/after report and inference identities. Final outputs are
`../tmp/m4-motion-center/coherent-shared-plane-{alice,hong}-v2/`; the earlier v1
trial initialized coupling from independent first-frame labels. V2 initializes
from source setup order and accounts for transitions into uncoupled frames.
