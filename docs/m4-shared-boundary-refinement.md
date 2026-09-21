# M4 shared-boundary ordering refinement

The CPU alpha raster includes triangle edges. Two compact regions of the same
source mesh can therefore report overlapping pixel centers on a shared edge,
even when their geometric intersection has zero area. Alice's source triangles
26 and 27 (`layer-003-depth-010/011`, common source vertices 15 and 26) give six
such pixels at time zero. This is a raster constraint issue, not evidence that
the texture or source mesh should move.

`depth_shared_boundary.BoundaryProbe` is an opt-in experimental wrapper. It keeps
the original raster measurement intact. For regions from the same source slot,
it checks every potentially intersecting triangle pair. A relaxation requires
common source vertices at identical sampled positions, nondegenerate triangles,
and exactly zero clipped intersection area. Positive area, unknown correspondence,
degeneracy, or resource exhaustion retains the original constraint. No area
tolerance is used. The 200,000 triangle-pair limit is shared across the run.

The effective overlap field may become zero; the original count and original
tile measurements remain diagnostic evidence. This is not a GPU top-left fill
rule implementation or proof of identical framebuffer blending. It does not
change the default worker, source images, weights, geometry, or depth inference.

## Frozen two-character recheck

`m4_shared_boundary_recheck.py` verifies the previously frozen report, inference,
observations and compact skeleton hashes before rebuilding exactly the same
ordering requests with this wrapper. It retains unknown/mixed labels and the
existing cycle-check limit. Source frames and held-order midpoint guards remain.

| Character | Refined pair/time samples | Triangle pairs checked | Remaining failures |
| --- | ---: | ---: | --- |
| Alice | 27 | 47 | 1 cycle-check limit, 54 visible order conflicts, 2 mixed-depth |
| Hongmeiling | 8 | 8 | 2 visible order conflicts, 11 mixed-depth |

Neither triangle-pair budget was exhausted. Neither run emitted a replacement
skeleton. Failure counts are unchanged; the shared-boundary issue is real but
does not explain the remaining cross-layer conflicts. No new Runtime captures
or visual acceptances were produced.

Hongmeiling's conflict at 0.433333 seconds includes visible overlap between
`layer-005` and `layer-009` (3,448 sampled pixels), the latter and arm region
`layer-001-depth-027` (113), and that region and `layer-005` (132). These constraints
cannot be satisfied by a single global slot ordering. The next step is to resolve
the per-surface depth/partition relationship with the third layer, retaining
continuity checks, rather than discarding positive-area overlap constraints.

The subsequent [same-frame pixel localization](m4-cycle-pixel-localization.md)
confirms simultaneous alpha support for these contradictory requirements. It
separates this case from cycles supported at different spatial positions.

Outputs are under `../tmp/m4-motion-center/shared-boundary-order-{alice,hong}-v1/`.
[Frozen audit](benchmark/m4-shared-boundary-evidence-v1.json) binds each raw report
to its prior report and source artifact. Reproduce from the repository with
`PYTHONPATH=src;tools`:

```powershell
python tools/m4_shared_boundary_recheck.py ../tmp/m4-motion-center/coherent-region-order-alice-v1 ../tmp/m4-motion-center/temporal-depth-partition-alice-bound-v1/observations.json OUTPUT
```

The output directory must be empty. Unit coverage includes unchanged original
raster evidence, a shared diagonal, a genuine folded-neighbor overlap, mismatched
common vertices, distinct source regions, degenerate geometry and budget fallback.
