# M4 complete arm-to-surface model routing

This experiment replaces manually naming a missing garment layer with an
inventory of every source attachment against each source-declared arm. It is
not a complete physical scene model: body/body relations still preserve setup
order, and several surface types have no measured depth model.

## Routing and safeguards

`depth_surface_inventory` inspects positive normalized influences on vertices
actually referenced by triangles. Unused vertices and a misleading slot bone
cannot change a mesh's role. It distinguishes same-side arms, same-side legs,
chest-only torso meshes, and the existing generated skirt-chain topology.
Skirt eligibility requires both upper/lower helpers, positive lengths and the
expected pelvis/parent links. This is model eligibility, not semantic approval
or evidence of real cloth depth. Unrecognized helpers remain unmodeled.

`depth_surface_checker` selects the existing explicit torso-plane model for
torso/skirt candidates and two-mesh source-depth envelopes for arm/leg or
arm/arm pairs. Leg eligibility may include a foot influence, but missing source
foot depth still becomes unknown; the classifier does not invent its endpoint.
Mixed sleeve helpers do not acquire arm depth merely because of their slot bone.

Two-mesh depth envelopes now support disjoint native-pixel tiles and triangle
callbacks. Callbacks inherit conservative global unknown contributors, including
other overlapping triangles; known geometry cannot hide an unknown contributor.
Tests compare whole-ROI, tiled and sparse-tiled results across actual tile
boundaries. Raster work remains bounded at 64 million pixels per relation.

Every source frame and midpoint is checked, including unmodeled surfaces. A pair
is omitted from inference only if all its checks have no overlap, or if no
supported model exists. The latter remains in diagnostics and retains ordinary
visible setup-order protection. It is not reported as known depth or authorized
to cross other attachments. Failures of an available model stay active unknowns.

`depth_region_constraints` resolves both endpoints when both source meshes are
partitioned. It omits region relations with no sampled support, leaving the
ordinary setup-order guard, and bounds expansion to 4,096 relations. Original
source-pair identities remain attached. Source geometry is unchanged, and the
coherent builder checks source/partition correspondence at all sampled times.

## Frozen complete turning clips

| Coverage / outcome | Alice | Hongmeiling |
| --- | ---: | ---: |
| Source surface pairs | 50 | 52 |
| Times per pair | 87 | 87 |
| Total checks | 4,350 | 4,524 |
| No overlap | 3,929 | 3,538 |
| Uniform front / back proxy | 52 / 67 | 123 / 386 |
| Mixed or insufficient depth | 208 | 129 |
| No available surface model | 94 | 348 |
| Setup-only visible source pairs | 2 | 4 |
| Expanded modeled region relations | 808 | 3,297 |
| Render regions | 245 | 324 |
| Visible order failures | 35 | 11 |
| Mixed-depth failures | 7 | 11 |
| Cycle-check limit failures | 1 | 0 |

All unmeasured checks in this run are missing-model cases, not budget failures.
Alice consumes 34,769,697 raster pixels in total; Hongmeiling 68,018,957 across
separately bounded pairs. Missing-model cases concern the hanging object for
Alice and front/back hair for Hongmeiling. Original bindings are not changed.

Hongmeiling's arm/arm overlap has 13 times, with mutually consistent opposing
classifications; Alice has 12. Hongmeiling no longer reports an ordering failure
at the previously localized 0.433333s and 0.45s, but new/remaining cycles involve
other body layers and held-order interval samples. Alice's aggregate failure
counts are unchanged. Neither run emits an accepted or replacement skeleton.
No new official Runtime capture or visual acceptance occurred.

The [coverage audit](benchmark/m4-surface-trace-evidence-v1.json) verifies the
complete source pair set, exact source/midpoint times, per-pair/global counts,
inventory, source artifact and trace identities, held-setup policy and coherent
output hashes. Both runs have zero overwritten hard proxy labels.

Local outputs are `../tmp/m4-motion-center/surface-traces-{alice,hong}-v1/` and
`../tmp/m4-motion-center/coherent-surfaces-{alice,hong}-v1/`. Reproduction uses
`m4_surface_traces.py JOB OUTPUT`, then `m4_coherent_region_order.py TRACE OUTPUT
--shared-boundaries --surface-routing`, with `PYTHONPATH=src;tools` and new output
directories. Reports remain isolated from current workbench candidates.

The next issue is joint consistency across surfaces sharing a plane model and
across held-order time intervals. Independently inferred per-body labels can
still contradict each other; a complete inventory alone cannot settle that.
