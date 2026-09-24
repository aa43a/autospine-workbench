# Region order intervals

The order-only compiler now supports an explicit animation and half-open time
interval. It keeps the partition's original setup order, moves the selected runs
at the start, and restores setup order at the end. Other animations are unchanged.
The static operation remains compatible. Existing draw-order tracks remain rejected
rather than silently overwritten.

This is an explicit candidate edit, not automatic depth inference or visual approval.
It does not alter bone weights, UVs, deformation tracks, or animation duration.
Depth QA sampling includes both sides of each draw-order boundary.

## Verification

- Nine Python tests passed across interval order, static order, and compaction.
- Reused the actual Alice source scene and 19-triangle selection from
  `tmp/region-order-live-v1`, with a test interval of 1 to 2 seconds. That interval
  is a technical probe, not an accepted semantic crossing interval.
- Official Spine core 4.3.13 checked 14 boundary, reverse-seek, and loop samples.
- Official core compared 478 frames / 730,384 vertex positions against the source:
  exact Float32 equality after compact vertex remapping.
- Target remains Spine 4.3.26; the tested runtime version is recorded separately.

Tools: `check-region-order-interval.mjs` and `check-region-order-core.mjs`.
Local evidence: `tmp/region-order-live-v1/interval-check.json` and
`interval-identity.json`.

## Remaining work

The interval is not yet exposed through the workbench draft, queue, or bundle path.
Those still offer the existing static operation. Next integrate the interval into
immutable job requests and the editor, then capture the switch frames for visual
review. Correct order and unchanged geometry do not prove a natural material seam.
Reach and Squat across the original three characters remain unfinished.
