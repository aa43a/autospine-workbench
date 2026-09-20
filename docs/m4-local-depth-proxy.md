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

## Official render-equivalence evidence

`tools/m4_depth_region_capture.py PARTITION_DIRECTORY OUTPUT_DIRECTORY` prepares
two isolated, content-addressed bundles from the exact source and partitioned
skeleton, retaining the original atlas/textures. It regenerates ideal and Float32
storage references and captures every selected frame using the existing official
Spine 4.3.13 WebGL harness. It does not attach a new accepted workbench candidate.

Hongmeiling now has fresh original/partitioned captures at all 115 source-frame
and midpoint times. Both passed the existing 0.001 px vertex threshold; maximum
error was 0.000116873 px. Slot counts are 27 and 31. The complete decoded PNG RGBA
comparison reports zero changed pixels in all 115 pairs under identical camera,
runtime, browser and harness identities. This verifies sampled rendering
equivalence under this capture environment, not continuous-time or corrected
depth ordering.

- Original isolated bundle: `e051d3f97624066e6500a2a5f8c4717239f1821a6671e159687ae6517ef0ef2d`.
- Partitioned bundle: `5b0a82605d7331e63337f884474ea2103b865520d302d586d30807cf090b1f60`.
- Exact evidence: `../tmp/m4-motion-center/depth-regions-hong-runtime-v1/equivalence.json`.
- Draggable comparison: `../tmp/m4-motion-center/depth-regions-hong-runtime-v1/comparison/index.html`.

The comparison rejects incomplete screenshot inventories, changed image bytes,
camera/time differences and mismatched capture environments. A changed alpha
channel alone fails equivalence. No depth assignment or visual approval is
inferred from equal images.

## Rendered-region ownership in the depth compiler

The opt-in `external-render-region-depth-review-v1-experiment` classifies only
vertices referenced by a region's triangles, while retaining the full vertex
arrays for deformation compatibility. Every positive influence participates;
even a tiny auxiliary-bone influence prevents classifying a region as chest-only.
The original whole-attachment policy remains unchanged. Source observations and
Schmitt state are rebuilt for each region's actual setup order instead of copying
a whole-layer order decision.

Run the local-order tool with `--refine-cycles --partition-slot layer-002
--partition-slot layer-005` for the verified Hongmeiling example. Four torso
targets are identified: two existing chest attachments and two chest-only render
regions. All six visible conflicts remain, now localized to `layer-002-depth-002`
at 1.333333 s and `layer-005-depth-002` at 1.366667–1.5 s. Both are mixed-weight
regions. Neither pure chest nor fully unmapped regions are the reported witness
in these samples. The 84 remaining ambiguous pair rows include invisible pairs;
they must not be presented as 84 visible failures.

Evidence: `../tmp/m4-motion-center/regional-depth-order-hong-v1.json`. No new
ordered candidate was generated. The next depth model must address chest/helper
mixtures rather than treating an entire skirt layer as chest or dropping its
visible ordering constraints.

## Explicit garment-plane and palm-depth experiment

`cloth_depth_plane.py` fits an affine depth plane to current target shoulder and
pelvis anchors using their exact source BVH depths, normalized to the same source
reference length as arm depths. Near-collinear projected anchors abstain. This
assumes planar cloth without thickness or out-of-plane motion; it is not a
reconstruction of the garment surface. The model only changes experimental depth
comparisons, not the exported mesh positions or current candidate.

`tools/m4_cloth_depth_probe.py JOB PARTITION_DIRECTORY ORDER_REPORT OUTPUT`
checks the recorded cycle frames and their next midpoints against this plane.
Identity checks bind the source artifact, request and partition skeleton; report
hashes record the ordering input. `--hand-depth` optionally adds the explicit
Mixamo wrist-to-middle-knuckle segment when its name and direct parent relation
are verified. Missing hands stay unknown. The assumed correspondence between
this source palm axis and the target hand axis is recorded separately; no finger
joint, animation channel or garment depth is fabricated.

The six Hongmeiling conflict intervals give 12 samples: two have no overlap and
ten remain uncertain. Adding actual palm observations increases known-front
coverage at 1.466667 s from 681 to 1,195 pixels and reduces unknown coverage from
1,035 to 521, but none of the ten visible samples becomes uniformly classifiable.
The existing endpoint-cap bound is not expanded to force success. No ordering
candidate is produced or accepted by this diagnostic.

Evidence: `../tmp/m4-motion-center/cloth-plane-hong-v1.json` and
`../tmp/m4-motion-center/cloth-plane-hong-hands-v1.json`. Tests cover plane anchor
interpolation, coordinate translation, degenerate views, relative depth against
a tilted plane, source FK continuity and verified/missing palm topology.
