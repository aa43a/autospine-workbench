# Local weighted segment depth experiment

`mesh_depth_proxy.py` reconstructs a candidate depth per weighted vertex from
source segment endpoint depths and the influence's setup-local bone-axis position.
It explicitly assumes planar cross-sections. It does not measure the character's
surface thickness, reconstruct hidden artwork, or assign depth to clothing helpers.

Each triangle is classified from all three vertex depths, conservatively using
the full triangle interval rather than a center sample. Only actual native-alpha
overlap contributes pixels. Missing segments, out-of-segment influences and invalid
weight sums abstain. Unknown coverage wins over known coverage; contradictory
front/back coverage remains ambiguous. No threshold or current draw order changes.

Run `tools/m4_local_depth_probe.py JOB_ID OUTPUT.json` from the repository with
`PYTHONPATH=src`. The tool verifies candidate character identity, source bundle,
source bytes/map identity and camera yaw. It evaluates up to the first 16 recorded
straddle failures; midpoint-only overlap abstains rather than borrowing the previous
source frame's depth. Output records the exact artifact, request digest and scope.

Three real structures were evaluated with the same algorithm at -30 degrees:

| First straddle, 0.166667 seconds | Behind chest under this proxy | Unknown | Total overlap |
| --- | ---: | ---: | ---: |
| Hongmeiling, ordinary bare arm | 852 | 99 | 951 |
| Alice, ordinary weighted arm | 1,162 | 778 | 1,940 |
| Huiye, wide sleeve | 0 | 31,373 | 31,373 |

All 16 sampled failures per character remain unresolved. The result narrows the
ordinary-arm problem but does not justify whole-slot reordering. Wide sleeves must
retain their separate cloth-depth uncertainty instead of inheriting arm depth.
The next integration must resolve remaining unknown support and validate actual
order changes across the full clip, target geometry and official Runtime. This
experiment is not connected to automatic adoption or human stage acceptance.

## Bounded endpoint-cap candidate

An additional opt-in profile, `weighted-segment-quarter-cap-depth-proxy-v1`, uses
constant endpoint depth for influences extending no more than one quarter of the
setup bone length beyond either endpoint. It does not extrapolate source depth
indefinitely. This is an explicit planar joint-cap modeling assumption, not a
measured anatomical surface. Missing hand/cloth segment evidence remains unknown.
The strict original profile is unchanged and remains the default.

The first Hongmeiling unknown pixels were supported by upper-arm influences just
outside the shoulder endpoint (normalized coordinates from -0.0029 to -0.1482).
The cap profile assigns all 951 overlap pixels a behind-chest proxy at that time.
Run with `--endpoint-caps --sample-limit 2048` to inspect the full recorded failure
inventory within the tool's bound. The same profile across three exact candidates:

| Character | Recorded straddles evaluated | Uniform behind-chest proxy | Still uncertain |
| --- | ---: | ---: | ---: |
| Hongmeiling | 28 / 28 | 28 | 0 |
| Alice | 28 / 28 | 0 | 28 |
| Huiye | 18 / 18 | 0 | 18 |

These counts cover existing discrete failure records, not all animation samples
or intervals. They do not resolve later arm/skirt ordering cycles, nor prove the
proxy agrees with a true 3D garment surface. No draw-order adoption is enabled.
Before integration, check held intervals/midpoints and all other order constraints,
then regenerate and capture any changed candidate. Results are in
`../tmp/m4-motion-center/local-depth-{hong,alice,huiye}-caps-all-v1.json`.

Artifacts: `../tmp/m4-motion-center/local-depth-{hong,alice,huiye}-v1.json`.
Tests cover interpolation, multiple influences, missing bones, out-of-segment
positions, unnormalized weights, opaque/transparent coverage, mixed depth and
resource limits. The original skeleton and textures are preserved.

## Held intervals and complete ordering constraints

`tools/m4_local_depth_order.py JOB_ID OUTPUT.json` now tests the bounded cap
assumption at source frames and interval midpoints, then reruns the complete
existing ordering constraints. Midpoint source depth is calculated by interpolating
BVH channels and running FK, not by averaging endpoint depths. Rotation-channel
intervals of 180 degrees or more abstain; this model is currently BVH-only.

An ambiguous row is refined only when every visible sample supports its already
held front slot. Unknown coverage, resource limits, opposite support and entirely
invisible sample pairs cannot clear that row. The experiment neither creates a
new ordering decision from the proxy nor changes the stored candidate.

| Character | Rows refined | Remaining visible ordering failures | New candidate |
| --- | ---: | --- | --- |
| Hongmeiling | 28 | 6 unmapped ordering conflicts | None |
| Alice | 0 | 28 straddles, 4 unmapped ordering conflicts | None |
| Huiye | 0 | 18 straddles, 4 unmapped ordering conflicts; 29 budget-limited checks | None |

Hongmeiling previously reported four conflicts because straddle failures stopped
some frame checks early. Refinement exposes six conflicts under the full check;
it does not establish successful ordering. Other unresolved ambiguous rows with
no overlap are distinct from visible straddle failures. Budget-limited checks are
unmeasured, never interpreted as absence of overlap.

Reports are `../tmp/m4-motion-center/local-depth-order-{hong,alice,huiye}-v1.json`.
No changed candidate was produced, no new Runtime capture is claimed, and no
visual acceptance was recorded. Frame-plus-midpoint evidence does not prove
continuous-time correctness. Tests additionally cover nonlinear FK depth,
camera yaw, ambiguous rotation intervals, clipped source time offsets, held-order
agreement and preservation of the original report.

## Distinguishing conservative order edges from visible cycles

An opt-in `--refine-cycles` experiment adds
`sampled-disjoint-cycle-refinement-v1`. It shortens a cycle using existing graph
chords, then tests its otherwise unmeasured setup-order edges at the source frame
and midpoint. Only edges with no alpha overlap at both samples may be removed.
Visible edges remain constraints; sampling errors and a 128-check bound abstain.
The original ordering profile remains the default. This does not infer new depth
for cloth, change pixels, or bypass source-depth conflicts.

The exact Hongmeiling candidate still has six failures from 1.333333 to 1.5 s.
No constraints could be removed. The first compact cycle is
`layer-002 -> layer-009 -> layer-001 -> layer-002`; the previously unmeasured
002/009 edge has 3,515 overlap pixels. The other five witnesses are
`layer-005 -> layer-009 -> layer-001 -> layer-005`, with 3,439–3,461 overlap pixels
on 005/009. Thus the failure is not explained solely by invisible setup-order
constraints. The first cycle combines source-frame and midpoint evidence for a
held interval; it is not asserted to be a simultaneous single-frame cycle.

See `../tmp/m4-motion-center/local-depth-order-hong-cycle-v1.json` for each exact
time, edge source and overlap sample. This establishes a conflict under the
current source-depth and retained visible-order assumptions, not ground-truth
physical depth. Resolving it requires revisiting local region ownership/depth or
region-level rendering rather than simply moving the entire arm slot forward.
There is still no new candidate or Runtime claim from this experiment.

## Region-level render prototype

`tools/m4_depth_region_partition.py JOB_ID OUTPUT_DIRECTORY --slot SLOT ...`
builds an isolated `ordered-weight-ownership-regions-v1` representation. It splits
consecutive runs of triangle ownership while keeping their original draw sequence.
Vertex arrays, weights, UVs and animation deformation index spaces are preserved;
each new slot shares the original texture path. This intentionally avoids merging
separated runs, which could change blending in folded/self-overlapping geometry.
Existing draw-order tracks, selected-slot timelines, linked meshes, clipping and
multiple skins are rejected rather than silently altered. Outputs are bounded to
128 regions and remain separate from workbench adoption.

Hongmeiling's exact candidate was tested on `layer-002` and `layer-005`. Six render
regions were generated: each source layer has chest-only, mixed and unmapped
triangle runs (8/232/324 triangles and 2/122/54 triangles respectively). Across
115 source-frame and midpoint samples, every retained vertex matches its original
animated position exactly (maximum difference 0). The source remains unchanged.
Files: `../tmp/m4-motion-center/depth-regions-hong-v1/{skeleton,report}.json`.

These regions provide separate future ordering targets; their depth remains
unassigned. This is not yet a corrected order or a captured Runtime candidate.
Splitting draw calls still needs official rendering/blending equivalence checks
before integration. Mixed and unmapped regions do not inherit chest depth merely
because they belong to the same clothing layer.
