# Equal-bracket depth hysteresis experiment

Temporal optimization left three different kinds of ambiguous transitions:
opposite hard proxy brackets, equal hard proxy brackets, and incomplete
brackets. This opt-in stage tests a stable-order hypothesis only for the second
case. It does not increase all smoothing costs or reinterpret ambiguity as a
measurement.

For each source triangle/body pair, find a maximal contiguous A run. Both
immediate boundaries must be F or B, and must agree. The run then holds that
label. Opposite boundaries, missing boundaries and N/U/M interruptions are
preserved. Observations, hard labels, unknown states, geometry and source motion
are unchanged. Every changed triangle/time is linked to its original run and
boundary times.

Equal endpoints do **not** prove there was no unobserved crossing inside the
interval. This is an explicit hysteresis candidate that can contradict spatial
regularization; its earlier optimization energy is not claimed to decrease.
Strict interval ordering and subsequent Runtime/visual acceptance remain
necessary. A blocked result is not adopted.

Add `--bracket-hysteresis` after `--temporal-labels` to the frozen quarter-trace
coherent experiment. `m4_bracket_hysteresis_audit.py TRACE BEFORE AFTER OUTPUT`
checks exact prior/source identities, every changed run, unchanged non-A labels
and the full order outcome. Use fresh output directories.

## Actual result: reject this candidate

The same Hongmeiling trace was replayed with 173 times and 8,996 surface checks.
Only nine equally bracketed runs on one arm changed, totaling 168 ambiguous
labels. All hard/unknown observations and labels remained unchanged.

Changing-order failures decreased from 12 to eight, but five ordering conflicts
and eight depth straddles were reported. At 0.5833335s, 0.6s, 0.6166665s and
0.633333s, previously passing sampled keys now fail. Only 0.6833335s and 0.95s
change from failed to passing. Two other times change failure categories rather
than pass. Consequently the audit records `reject_regression`; fewer temporal
flips are not evidence of an overall improvement.

The [source-bound audit](benchmark/m4-bracket-hysteresis-v1.json) verifies each
modified run and records the introduced/resolved failure times. No skeleton
was emitted, no official Runtime recapture occurred, and the workbench default
is unchanged. The experiment remains opt-in for reproduction, not recommended
for adoption. It shows that independent temporal holds cannot replace joint
spatial ordering constraints. The frozen output is
`../tmp/m4-motion-center/coherent-brackets-hong-v1/`.
