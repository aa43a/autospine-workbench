# Temporal stabilization of ambiguous depth labels

Held-interval checks found 15 changing-order witnesses in the Hongmeiling turn.
Every witness involved an ambiguous label at one or both times. Adding order
keys immediately could therefore encode inferred flicker, not a real crossing.

This opt-in experiment solves labels across the complete sampled time sequence.
Only A (ambiguous) states are variables. F/B observations remain unchanged;
unknown, mixed and nonoverlap states remain unchanged and do not provide
temporal anchors. Spatial triangle adjacency, consecutive time samples and
identical-plane ambiguous pairs contribute soft disagreement costs of 8.
The existing inferred label contributes a preference cost of 1.

These costs describe an experimental objective, not calibrated confidence.
Labels do not become measurements after optimization. No vertices, weights,
textures or source animation rotations are modified.

## Bounded solver

The graph is limited to 32,768 ambiguous nodes and 131,072 edges. Connected
components within the existing 4,096-node / 16,384-edge cut limits are solved
directly. Larger components use conditional cuts of at most 1,024 nodes, with
forward/reverse sweeps and at most eight iterations. A complete sweep must not
increase the full component energy. Convergence means **block-local stability**,
not global optimality. If convergence or cut resource limits fail, that
component retains its original labels.

Afterward, source geometry correspondence and strict held-interval ordering
still run. The original observed states and pre-temporal labels remain in the
artifact. Any remaining ordering failure prevents skeleton emission.

## Reproduction

Add `--temporal-labels` to the existing `m4_coherent_region_order.py` experiment
with `--surface-routing --shared-boundaries --shared-planes --interval-depth`.
Use a frozen quarter-sample trace and a new output directory. Run
`m4_temporal_label_audit.py TRACE BEFORE AFTER OUTPUT_JSON` to verify source and
prior identities, non-A preservation, actual graph energy and order outcomes.

## Actual same-source comparison

The Hongmeiling quarter-sample experiment uses the same 173 times and 8,996
surface checks as the interval baseline. There are 7,078 ambiguous variables.
The smaller arm components are solved directly; the 5,943-node component of
the other arm reaches block-local stability in two sweeps. No component hits
an iteration or resource limit.

Only ambiguous labels change: 247 on one arm and six on the other. Their graph
energies decrease from 3,608 to 3,495 and 6,768 to 6,742 respectively. Render
regions decrease from 382 to 367; retained relations from 2,619 to 2,500.
The strict-order outcome still fails: changing-order intervals decrease from
15 to 12, while seven depth-straddle failures remain. Neither energy nor
diagnostic count is a measure of rendered visual quality.

The 12 remaining interval witnesses contain 14 source-triangle tracks. Looking
outward through contiguous ambiguous observations, two tracks have opposite
hard proxy states at their boundaries, five have equal hard states, and seven
have incomplete boundaries (unknown/nonoverlap or clip ends stop the search).
These are distinct follow-up cases; stronger uniform smoothing is not justified.

The [frozen audit](benchmark/m4-temporal-depth-labels-v1.json) preserves these
per-triangle contexts, verifies unchanged observations/non-A labels and
recomputes actual graph energies. The result remains an isolated blocked
experiment at `../tmp/m4-motion-center/coherent-temporal-hong-v1/`, with no
replacement skeleton, fresh Runtime capture or visual acceptance.

The next isolated hypothesis is [equal-bracket hysteresis](m4-bracket-hysteresis.md).
