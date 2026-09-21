# Locate incomplete overlap checks

Order solving stops at the first failure within each sampled frame. Therefore,
its failure list alone does not enumerate every alpha-overlap measurement that
was skipped earlier. A visible straddle can hide a later pair's exhausted raster
budget from the operator's location list, even though aggregate completeness
already correctly remains false.

`depth_failure_records.collect` combines order failures and explicitly unmeasured
pair samples, deduplicating by time, reason and unordered pair. It does not infer
missing measurements or rewrite stored evidence. New overlap reports also retain
the raster exception's rectangle, required pixels and remaining budget.

The read-only depth status includes bounded records for each category separately.
The existing first-100 list remains available; per-category filtering no longer
loses resource failures behind 100 earlier conflict records. All counts are
diagnostic observations, not distinct visual defects or an error rate.

## Actual verification

Huiye Kimodo torso candidate `motion-223847a1e58e45cfa2d7764ccc6ef282`, artifact
`32859aa579178b38d2d2c0b76e4fe6679a361d82faaf67332bd24b1c5955cef0`, retains its
original animation and readiness. The current diagnostic read now exposes 120
depth-conflict records and 27 resource-limit records. The first resource limit
is at 3.1 seconds for `layer-002-component-0000` against `layer-005`.
Its original report used 63,920,518 of the 64,000,000 pixel budget. No budget or
quality threshold was changed. Historical cached reports are not rewritten.

The live Chrome category filter displays the previously hidden resource records
and exact candidate timeline links. Tests cover early conflict masking,
deduplication, category truncation, preserved source evidence and retention of
raster-budget location without fabricating zero overlap. This change explains
incompleteness; it does not finish the missing measurements or repair depth.
