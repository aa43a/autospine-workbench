# Full-clip garment ordering experiment

This extends [local depth diagnostics](m4-local-depth-proxy.md) without changing
published candidates or the default adapter. Use `m4_local_depth_order.py` with
`--cloth-constraints`, explicit partition slots, and optionally `--refine-cycles`.

`cloth_depth_constraints.py` evaluates every arm against mixed and unmapped
garment partitions at source frames and interval midpoints. It combines the
declared planar garment, mesh-supported hand axis, observed source fingertip,
and bounded secondary-influence contracts. A held order requires all visible
checks in the interval to agree. Missing evidence, conflicting classifications,
and resource failures remain explicit; no-overlap checks do not invent depth.
The resulting constraints identify their origin as `garment_plane_interval_model`.

Each pair has a bounded raster budget. Verified overlap results may be reused
by the order compiler only for the identical document, textures and animation.
Conflicting cache entries fail. This avoids charging duplicate raster work while
retaining individual pair budgets and unknown results.

## Hongmeiling raise-arms, oblique -30 degrees

Exact candidate: `motion-6d7be7b37ac141c1906cf28ca5eb4c74`, artifact
`1842fe3961713e9c7b32f3463be804749b7268208f1540a52a2c91053379434f`.

Evidence: `../tmp/m4-motion-center/full-cloth-depth-order-hong-v2.json`.
The 58 source frames and 57 midpoints produce 920 checks over eight pairs:
894 have no overlap, 26 uniformly support the arm in front, and none are
unmeasured. All 920 overlap results are reused by ordering. The previous run's
ten duplicate-work budget failures disappear without changing quality limits.

Five visible ordering conflicts remain at 1.366667, 1.4, 1.433333, 1.466667 and
1.5 seconds. Their cycle involves `layer-003` (right leg),
`layer-005-depth-002` (garment), and `layer-001` (right arm). Consequently no
reordered candidate is emitted and no new Runtime capture or adoption is claimed.
The next missing evidence is arm/leg ordering, not more garment-only sampling.

These measurements validate the declared proxy at sampled times, not continuous
motion, anatomical depth, or human visual acceptance. Tests cover midpoint
disagreement, explicit unmeasured results, source-time sampling, original-data
preservation, and identity-bound cache reuse.

## Arm/leg cycle evidence

`m4_limb_depth_probe.py` verifies the exact partition and ordering identities,
then evaluates recorded arm/leg cycle edges at source frames and midpoints.
Mapped thigh/calf source axes are exposed separately from the existing arm-only
sampler, preserving its default behavior. `mesh_pair_depth.py` rasterizes each
triangle's conservative depth envelope in its clipped native-pixel bounds. Both
attachments must clear the depth margin throughout their envelopes. Unknown
triangles cannot be hidden by known triangles that overlap them; each attachment's
unknown contribution is reported separately. Work remains pixel-budget bounded.

Actual evidence: `../tmp/m4-motion-center/arm-leg-depth-hong-v2.json`.
Across ten samples, one supports arm-in-front, one has no overlap, and eight
remain uncertain. In all eight, uncertainty is entirely supported by right-leg
mesh `layer-003`; right-arm `layer-001` has zero unknown overlapping pixels.
Known overlapping pixels all support arm-in-front, with no opposite or ambiguous
known classifications. This does not justify applying that order to the unknown
pixels. The next investigation is the leg's influence-axis correspondence.

Sixteen focused tests pass, including two-sided interval separation, reversed
order, unknown/known triangle overlap, non-clearing intervals, resource failure,
and declared leg endpoint extraction. No new candidate or Runtime capture is
produced by this diagnostic.

## Explicit leg influence envelope

The cause report `../tmp/m4-motion-center/arm-leg-depth-hong-v3.json` attributes
all eight uncertain samples to `calf_r` influences outside the existing quarter
axis cap. No additional missing source segment is implicated in this overlap.

`--leg-intervals` enables a separate same-leg envelope contract. It requires
declared thigh/calf source endpoints to agree and the target calf to be directly
parented to the same-side thigh. Only same-side thigh/calf influences qualify;
foot, unrelated, missing, invalid, and wholly out-of-axis support remain unknown.
Every positive secondary weight contributes its full observed-chain interval;
weights and exported geometry are unchanged. Arm-only behavior remains default.
This remains a depth-model assumption rather than a measured skin surface bound.

On the same ten samples, nine now uniformly support arm-in-front and one has no
overlap. Evidence: `../tmp/m4-motion-center/arm-leg-depth-hong-interval-v1.json`.
Eleven focused regression tests pass. These local outcomes do not yet establish
full-clip arm/leg order, a reordered candidate, or Runtime visual acceptance.
The next step is complete-motion integration of the explicit pair constraints.

## Full-clip limb constraints and official capture

`--limb-constraints` now evaluates all identified arm/thigh-or-calf slot pairs,
with the same held-frame/midpoint rule and explicit unknown handling. Source time
offsets must agree, raster work is bounded independently per pair, and verified
overlap entries are reused only for the same order probe identity. The new model
is opt-in; existing candidate adapters and reviewed decisions remain unchanged.

`../tmp/m4-motion-center/full-limb-depth-order-hong-v1.json` contains four pairs
over 115 times: 451 no-overlap checks, nine uniform-arm-front checks, and zero
unmeasured checks. Combined with garment constraints, full ordering has no
failures and emits one draw-order key. This covers this exact clip and character,
not all three cohort structures or the other action categories.

`m4_depth_order_capture.py` checks that the candidate differs from the verified
partition only by the recorded draw-order keys, then captures isolated immutable
bundles. Original and reordered candidates each pass 115 official Runtime frames;
the latter has 31 slots and maximum vertex error 0.00011687258783135879 px.
Runtime also checks the actual draw order. Evidence and draggable same-frame
comparison: `../tmp/m4-motion-center/full-limb-depth-runtime-hong-v1/`.
Candidate bundle: `5bf5df3ddc0d5a366380b71d89d8a19bdf0a7df5ba2394b65d3244faec64abca`.

Eighteen focused tests pass, including source/midpoint disagreement, preservation
of originals, identity-bound reuse and unmeasured samples. This is a captured
experimental candidate, not human visual acceptance or a production default.
Remaining integration includes broader cohort checks and workbench exposure.

## Matched three-structure check

The same raise-arms source and -30 degree view were run on the frozen Alice and
Huiye candidates. Alice partitions `layer-005`; Huiye partitions `layer-004`.
No per-character depth margin or weight change was introduced.

| Character | Cloth checks | Arm/leg checks | Ordering result |
| --- | --- | --- | --- |
| Hongmeiling | 894 no overlap, 26 front | 451 no overlap, 9 front | Candidate; 115 Runtime frames pass |
| Alice | 425 no overlap, 28 front, 7 uncertain | 460 no overlap | No candidate; 29 visible straddle failures |
| Huiye | 351 no overlap, 91 uncertain, 18 unmeasured | Not applicable: no identified leg slots | No candidate; 25 visible straddles, 32 order-budget failures |

Evidence: `../tmp/m4-motion-center/full-limb-depth-order-alice-v1.json` and
`full-limb-depth-order-huiye-v1.json`. The cloth counts and ordering failures have
different units; they must not be summed into an error rate. Alice's first
ordering failure involves the left arm and chest-bound `layer-006`, so fixing
arm/leg order alone cannot resolve it. Huiye's missing leg pair is reported as
not applicable, not a successful anatomical-depth measurement or a fatal error.
Its unmeasured raster work remains separate from measured uncertainty.

Thirty-four focused tests pass, including absent leg pairs and capture rejection
of unrelated geometry edits, changed source identities, and unmeasured evidence.
This comparison limits the current algorithm's support claim to the captured
Hongmeiling case. Next work must improve torso/arm depth evidence and bounded
raster efficiency before exposing a broadly applicable automatic workflow.

## Torso-plane refinement option

`--torso-plane` opts into `torso-plane-hand-interval-held-order-v1-experiment`.
Previously ambiguous arm/chest rows can use source torso anchors, supported mesh
hand axes, observed source fingertips and same-arm weighted depth intervals.
The old zero-reference segment proxy remains the default. This mode preserves
the held source order: both the frame and midpoint must support that order before
ambiguity is cleared. Opposite depth, model degeneration, missing evidence and
budget failures cannot silently change the order or become no-overlap results.
The planar torso assumption is recorded explicitly and mesh geometry is untouched.

Actual Alice evidence: `../tmp/m4-motion-center/full-torso-depth-order-alice-v1.json`.
The refinement checks 112 source/midpoint samples: 56 no-overlap and 56 still
requiring more local ordering evidence. No held rows are cleared; full ordering
retains 29 visible-straddle failures. This result is not a resource timeout:
refinement consumes 12,260,398 raster-budget pixels.

At 0.166667 seconds the arm/chest overlap has 1,940 pixels: 255 support front,
169 support back, 1,516 are within the uncertain boundary envelope, and zero
are unknown. At the next midpoint both front and back support remain. The new
model therefore exposes conflicting local surface-order requirements rather than
just missing hand depth. A single whole-attachment swap cannot satisfy these
modeled relationships. Next candidates should investigate local render regions
or alternative projection; widening the depth margin is not a justified repair.
Seventeen focused tests cover default compatibility, preserved held order,
source-midpoint identity, plane-relative classification and degenerate rejection.

## Rendered-vertex bounds

`--rendered-bounds` restricts each experimental pair ROI to vertices referenced
by its actual triangles. Partition attachments deliberately retain the complete
source vertex array for deformation identity; unused vertices must not enlarge
the raster work region. The old all-vertex behavior remains the default. Reports
record `bounds_policy`, and pair constraints use the order probe's same policy
when caching overlap results. Invalid triangle indices fail explicitly.

Alpha threshold, depth margin, pixel budget, UV interpolation and original mesh
arrays are unchanged. Tests compare identical overlap counts with unused far-away
vertices, verify the reduced budget cost, and cover empty/invalid index sets.

Matched Huiye evidence: `../tmp/m4-motion-center/full-render-bounds-order-huiye-v1.json`.
The four cloth pairs now complete all 460 checks: 361 no-overlap, 99 uncertain,
zero unmeasured (previously 18 unmeasured). Aggregate pair raster cost drops from
232,410,884 to 103,969,710 budget pixels, approximately 55 percent, without
increasing any budget. The additional completed samples expose ten no-overlap
and eight uncertain results; neither category is counted as automatically accepted.
Whole ordering still reports 27 visible straddles and 29 budget failures, so no
candidate is emitted. These remaining failures include other ordering work and
must not be mistaken for the now-complete cloth pair checks. Thirty-seven
focused regression tests pass.

## Refinement overlap reuse and resource attribution

`--reuse-refinement-overlap` copies completed refinement overlap measurements into
the order probe. Identity checks require the same document, files, animation and
bounds policy; conflicting entries fail, and copied records are detached from
the producer. The default remains unchanged. Huiye reused 92 records, but the
matched full run still has 27 straddles and 29 budget failures:
`../tmp/m4-motion-center/full-shared-depth-order-huiye-v1.json`.

Budget errors now carry structured pair/time/ROI/cost evidence while retaining
their legacy reason code. A direct reproduction of the left-sleeve/chest pair
at 0.133333 seconds shows ROI `[609,224,337,784]`, or 264,208 pixels, exceeding
the single-ROI cap 262,144 despite 63,999,648 total pixels remaining. Thus this
failure cannot be fixed by more shared results or a larger aggregate budget.
The next resource change should tile native-pixel work while retaining bounded
total cost, alpha sampling and unresolved-depth semantics.

## Bounded native-pixel tiles

`--tiled` enables `native_pixel_tiles_256_v1`: disjoint 256-by-256 native-pixel
tiles, including partial boundary tiles, with at most 64 tiles per pair ROI.
Pair rasterization and arm/plane depth classification operate per tile; the
aggregate pixel budget is unchanged and charged for actual work. Empty tiles
need no additional classification. Coordinates, UV filtering and alpha>=8 remain
identical. A tile-limit failure or total-budget failure is explicit. Cached
measurements cannot cross the tiled/legacy policy boundary.

Thirty-eight tests pass, including direct-versus-tiled counts, unknown triangle
classification across tile seams, negative origins, partial edge tiles, aggregate
resource failure, policy identity, and retained legacy single-ROI behavior.

Actual Huiye evidence: `../tmp/m4-motion-center/full-tiled-depth-order-huiye-v1.json`.
At 0.133333 seconds the formerly oversized left-sleeve/chest ROI uses eight
tiles and measures 33,853 overlapping pixels, exactly matching an independent
direct-mask calculation. Complete ordering has zero raster-budget failures,
but retains 45 `visible_depth_straddle` failures and emits no candidate.
This does not mean every upstream depth calculation completed: held-order
refinement still has six unmeasured samples under its separate 64M total budget
(56 no-overlap and 50 uncertain); it consumes 63,941,350 budget pixels and reuses
107 completed pair measurements. Cloth constraints remain fully measured:
361 no-overlap and 99 uncertain. The next resource issue is the refinement total
budget; measured sleeve-depth uncertainty remains a separate modeling limitation.

## Per-pair refinement resource policy

`--pair-budgets` opts into `per_pair_refinement_budget_v1`. Each arm/torso pair
has its own 64M raster budget, with a maximum of 16 pairs and 512 source frames
for the operation. Reports retain per-pair and summed cost, and completed overlaps
are shared with the exact order probe. This increases allowed aggregate work in
proportion to pair count; it is a resource allocation policy, not a claim of
faster computation or a relaxation of depth/alpha quality checks. Legacy shared
budget behavior remains default. A regression fixture verifies that one pair
cannot starve the next, the full cost is reported, and oversized pair sets fail.

The first matched Huiye run (`full-pair-budget-order-huiye-v1.json`) still left
six samples unmeasured: one sleeve/chest pair alone consumed 63,974,290 pixels.
This evidence rules out inter-pair starvation as the remaining cause here.

Tiled probes now retain the most recent pair's opaque intersection tiles as
read-only arrays, allowing the immediately following depth classification to
reuse the already charged masks. At most one pair, bounded by 64 tiles, is kept;
frame or pair changes cannot reuse stale masks. Scalar report caching remains
separate. This saves duplicate alpha work without omitting depth classification.

Matched evidence: `../tmp/m4-motion-center/full-alpha-reuse-order-huiye-v1.json`.
All 112 refinement checks complete: 56 no-overlap, 56 uncertain, zero unmeasured.
Total refinement cost is 49,439,554 pixels, with 49,406,958 for the large
sleeve/chest pair. All 112 overlap results are available to ordering. Cloth
constraints also complete (361 no-overlap, 99 uncertain). Whole ordering still
has 45 visible-straddle failures and no candidate; these are now retained model
uncertainties rather than unmeasured resource failures. Thirty-nine focused
tests pass. This establishes a measured unsupported case for the workbench's
exception flow, not a reason to raise quality thresholds or silently adopt it.
