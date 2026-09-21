# Depth evidence for held draw-order intervals

An order key applies until the next key. The existing experiment checked alpha
overlap at the key and interval midpoint, but used the key's inferred depth for
both. If a region was nonoverlapping at the key and entered a body region at the
midpoint, its old inferred label did not establish the new overlap's depth.

The optional strict interval path associates each visibility check with depth
evidence at that **same time**:

* A newly visible midpoint uses its own front/back label.
* Missing midpoint evidence fails with `held_interval_depth_missing`.
* Unknown, mixed, or contradictory no-overlap evidence remains unresolved.
* Opposite relationships at two visible samples fail with
  `visible_depth_order_changes_within_interval`, retaining both witnesses.

The last case needs an additional order key and more interval evidence; it is
not repaired by borrowing either endpoint label. No continuous-time correctness
is claimed from these bounded samples.

## Experiment

`m4_surface_traces.py JOB OUTPUT --subdivisions 4` measures all source keys and
their quarter, half and three-quarter times against every target surface. It
keeps the existing per-pair raster and inventory limits. Missing models and
budget failures remain explicit. The original motion and character are verified
before sampling, and each evidence file receives a content hash.

`m4_coherent_region_order.py TRACE OUTPUT --surface-routing --shared-boundaries
--shared-planes --interval-depth` builds region signatures over all those
samples. Alternating samples become order keys; the intervening samples provide
independent held-interval evidence. Their times must match the exact midpoints.
Geometry correspondence is checked at every trace sample before ordering.

To keep the existing 4,096-relation limit, partition-to-partition pairs can be
omitted when one side has no observed overlap at every common sample, or when
their same-time mesh bounds are disjoint at every sample. Bounds include a
one-pixel margin on each side. Unknown support is retained, time inventories
must match, and the ordinary setup-order overlap guard still runs. This is a
bounded-sample rejection, not a claim about all continuous intermediate times.

The default workbench path and historical results are preserved. This optional
CPU experiment emits no skeleton when any order check fails. A passing order
would still require fresh official Runtime rendering and visual acceptance.
Denser sampling also changes temporal inference; outcome differences are not
attributed solely to the interval lookup fix.

## Actual Hongmeiling turning clip

The same frozen artifact `74cbc377399f46070f9744a32e903b0488af2f9cd04112b0027adcd4ce45d8c4`
was measured at 173 times for all 52 surface pairs: 8,996 checks. The 692
unmeasured checks all lack a surface model (hair), rather than exhausting a
raster budget. Those pairs retain setup order without a depth claim.

The experiment produces 382 unchanged-geometry regions and 2,619 relations.
Time support excludes 48 relation pairs; disjoint sampled bounds exclude 2,258.
The original 4,096-pair limit stays intact. The order result remains blocked:
15 held intervals have changing inferred order and seven have depth straddles.
All 15 changing-order witnesses include ambiguous evidence at one or both
samples; none is a reversal supported solely by hard F/B proxy observations.

This changes the next action: stabilize temporally ambiguous inference before
automatically adding draw-order keys, which could otherwise encode flicker.
Earlier ordering-cycle failures are not proven eliminated because an interval
failure can stop that key's checks before the full graph is evaluated.

The [source-bound audit](benchmark/m4-held-interval-depth-v1.json) records coverage,
partition and inference identities, pruning counts and each reversal's observed
states. There is no replacement skeleton or new Runtime capture. Local outputs:
`../tmp/m4-motion-center/surface-quarter-hong-v1/` and
`../tmp/m4-motion-center/coherent-interval-hong-v1/`.
