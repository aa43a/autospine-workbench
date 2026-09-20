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

Artifacts: `../tmp/m4-motion-center/local-depth-{hong,alice,huiye}-v1.json`.
Tests cover interpolation, multiple influences, missing bones, out-of-segment
positions, unnormalized weights, opaque/transparent coverage, mixed depth and
resource limits. The original skeleton and textures are preserved.
