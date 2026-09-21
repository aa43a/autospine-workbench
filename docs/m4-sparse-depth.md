# Conservative sparse alpha-overlap experiment

The optional `Probe(..., tiled=True, sparse=True)` intersects conservative
triangle-bounding-box occupancy on a 64-pixel grid. A cell is omitted only when
at least one mesh has no triangle box intersecting it. Retained cells are
disjoint and use the original world pixel centres, UV interpolation, bilinear
alpha sampling and alpha >= 8 threshold. This is not image downsampling or a
confidence threshold change. Large triangles can retain substantial empty area;
the optimization deliberately favors conservative coverage.

Rendered triangle bounds exclude unreferenced vertices. At most 4,096 occupancy
cells are considered per pair/frame. The same global 64,000,000 sampled-pixel
budget applies; cache reuse rejects different sparse policies. Resource failures
remain unmeasured, with actual sparse required pixels recorded separately from
the enclosing rectangle area.

This remains an opt-in probe, not the default worker policy. It does not modify
candidate meshes, UVs, weights, draw order or acceptance. Source-sample completion
does not prove held-order midpoints, local depth models or Runtime appearance.

## Reproduce against an immutable candidate

```powershell
$env:PYTHONPATH='src;tools'
python -X utf8 -u tools/m4_sparse_depth_probe.py MOTION_JOB OUTPUT_JSON
```

The tool verifies the addressed artifact and skeleton/depth identities, rechecks
every recorded pair/source sample, and compares exact overlap-pixel counts where
both old and new measurements exist. Previously unmeasured rows remain in the
output with their original evidence and the new measurement. Any disagreement
terminates with an error after saving the report. It does not silently replace
the old task or label newly measured overlaps as correct depth ordering.

Tests cover disconnected geometry, noninteger transformed boundaries, transparent
textures, unchanged input, exhausted budgets and cache-policy separation.
Existing tiled raster, guarded ordering and local-refinement tests also pass.

## Actual candidate probes

All four immutable candidate probes completed under the same 64-million pixel
budget. Their 1,022 previously measured pair/frame observations agree exactly;
54 previously unmeasured observations were recovered. None remain unmeasured
within this source-sample-only probe. Twenty-six focused tests passed.

| Candidate | Original pixels used | New pixels used | Recovered samples |
| --- | ---: | ---: | ---: |
| Huiye Kimodo wave | 63,920,518 | 56,106,458 | 27 |
| Huiye FBX raise, -30 degrees | 38,109,478 | 35,060,184 | 27 |
| Hongmeiling Kimodo wave | 3,512,286 | 2,946,366 | 0 |
| Alice Kimodo wave | 8,273,368 | 6,167,146 | 0 |

Original budget totals cover fewer measurements in the two Huiye cases. This
experiment combines rendered triangle bounds, bounded tiling and sparse cells;
it does not attribute all recovery solely to sparsity. Tiling can also address a
single-rectangle limit without increasing the global sampling budget.

Exact task/artifact/report identities and summaries are in
`benchmark/m4-sparse-depth-evidence-v1.json`. Full per-sample reports reside in
`../tmp/m4-motion-center/sparse-depth-*-v1.json`. Original candidates and stage
reviews are unchanged. The next integration must re-evaluate order midpoints and
any local depth constraints under this policy; these measurements alone cannot
clear the existing depth-conflict gate.
