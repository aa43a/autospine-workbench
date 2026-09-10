# Retained sleeve weights: edge-budget experiment

2026-09-10. This is a candidate experiment, not production adoption or Runtime evidence.

`tools/solve-retained-sleeve.py --edge-budget` applies the existing area/edge displacement
lower bound and unchanged cap to the exact retained weights. Each motion must pass the
existing nonregression gate against its retained baseline; rejected motions remain exact.
The solver's inner gate and outer retained-baseline gate are recorded separately.
There are no character-name rules or relaxed QA thresholds.

Bayunlan source: `51a5cf467884befcf11fc93b65e10edddae0cc2029ec2abb5f65af4c408eaaa5`.
Candidate: `cdb8fe6759864d5483b7c2134085e86fab8b358a9c3067bc649156a0065822ff`.
Local review: `tmp/r3s-retained-edge-joint/bayunlan/index.html`.

| Right sleeve motion | Baseline failed ticks | Retained trial failed ticks |
| --- | ---: | ---: |
| hand | 70 | 30 |
| combined_pp | 21 | 0 |
| combined_mm | 23 | 2 |

All 33 correction-key poses pass for these three motions. The 30 hand and 2 combined_mm
failures occur between keys, among the same 129 QA samples. They have zero inversions;
the failing metric is minimum area ratio (hand minimum 0.302539338965316,
combined_mm minimum 0.49625842489296235, required 0.5). This identifies temporal
compression rather than a reason to lower the area threshold. The next correction
must address interpolation and still verify the actual exported animation.

The other two right combined-motion trials regress area or stretch and are rejected.
Left-sleeve failed counts do not improve; several metric improvements are retained,
but the sleeve remains blocked. Its fixed-endpoint counterexample remains unresolved.
No unknown region has been relabeled by this experiment.

Verification checked unchanged weights, setup vertices, triangles and helper for both
regions; all 14 retained motions pass the nonregression gate, all rejected tracks remain
byte-equivalent as JSON values, and each track retains 129 QA samples. Candidate authority
and geometry-failure status remain intact. Joint-solver and boundary-budget tests: 7 passed.

The diagnostic-image xyxy/xywh bug was independently fixed in `04e620e`.
Its numerical report identities remain unchanged; it did not alter this solver input.
The original Huiye/Uuz Runtime artifacts are unchanged by this experiment.

## Neighbor-seeded projection

The opt-in `--smooth-seed` experiment initializes each free vertex from a weighted
average of neighboring corrective offsets (1/4, 1/2, 1/4), then projects it through
the same geometry solver and capped displacement budget. Fixed vertices ignore the
seed. Cycle setup poses at ticks 0, 64 and 128 use the original initialization.
The default solver path remains unchanged. This adds no new key times or QA tolerance.

The first pass is `778d5c6a80bd94ee5ce3dd948a7d31c402c61e327fd1d0740e67ed879cdd33f3`:
right hand failed samples 30→8, combined_mm 2→0; left combined_pm 100→98.
The second pass is `4683f82c82127744726069eb866214b2ee666baad36c885bd13b2c9690c8967d`:
right hand 8→2. Remaining hand failures are triangle 428 at ticks 18 and 46,
minimum area ratio 0.48994052294461543. Neither has inversion or excess edge stretch.

Both passes were checked against their exact retained source: all 14 selected motions
are nonregressing, rejected motions are unchanged, setup poses reconstruct within 1e-7,
and weights, topology and helper structure remain identical. These reports remain
blocked candidates. No framebuffer validation is claimed for these changes.

Third pass: `d4ee91b56b8c5915a4d5f636058aef47518659a0e22a2853d5b661d601aaa6c8`,
review `tmp/r3s-neighbor-seed-pass3/bayunlan/index.html`. Hand failures 2→0.
Bind-data identity and all retained nonregression gates were checked again.
An independent 513-point replay of sine FK plus linear corrective-key interpolation
found zero failures in the five right-sleeve motions currently passing the 129-point gate:

| Motion | Minimum area ratio across 513 points |
| --- | ---: |
| forearm | 0.592604628235273 |
| hand | 0.5097569177217176 |
| cloth | 0.5348362728200675 |
| combined_pp | 0.5057111343838443 |
| combined_mm | 0.5215587736296418 |

This checks denser CPU samples, not continuous time or exported Runtime interpolation.
The other two right motions and left-sleeve failures remain blocked. The three-pass
experiment is explicitly source-linked, not an unbounded automatic optimization loop.
Validation: 11 cloth tests, 5 envelope/helper tests and 3 source-quality tests passed.
