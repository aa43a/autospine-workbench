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
