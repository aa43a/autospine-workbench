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
