# Frozen full-matrix supplemental depth check

This run applies the same bounded pixel-interval diagnostic to all 24 unchanged
targets in `benchmark/m4-cohort-plan-v3.json`, using the exact candidates in
`../tmp/m4-motion-center/cohort-state-v3.json`. It does not replace failed
candidates, rebuild animations, change views, trim clips, or recapture Runtime.

Run with `PYTHONPATH=src;tools`:

```powershell
python tools/m4_local_depth_matrix.py docs/benchmark/m4-cohort-plan-v3.json ../tmp/m4-motion-center/cohort-state-v3.json ../tmp/m4-motion-center/local-depth-matrix-v1 --limit 3
```

Each invocation processes at most three unfinished cells. Resume validates the
plan/cohort/profile identity and completed report hashes. New work also verifies
the live task's candidate, original raw source, frozen character and immutable
MotionIR bundle. Completed diagnostics are registered on their original tasks
as supplemental evidence; no acceptance records are written.

The HTML matrix includes pending cells and links to the exact workbench tasks.
State and reports: `../tmp/m4-motion-center/local-depth-matrix-v1/`.

The first completed group is breathing across all three structures:

| Character | Pair/frame records | Result |
| --- | ---: | --- |
| Alice | 598 | 598 unresolved local-depth records |
| Huiye | 598 | 95 unresolved, 503 unmeasured |
| Hongmeiling | 1196 | 897 unresolved, 299 no visible overlap |

These are sampled model records, not independent observations or visual error
rates. The report retains the specific cause and missing-data reason for every
record. No Runtime or human acceptance claim follows from this supplemental
check. The other 21 cells remain pending in this run.

A checkpoint regression test confirms exact results are reused and changed
report bytes or profile identity are rejected before reuse. The batch does not
restart a still-running process on an observation timeout; resume only after the
original process is confirmed terminal.
