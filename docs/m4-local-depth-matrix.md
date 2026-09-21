# Frozen full-matrix supplemental depth check

This run applies the same bounded pixel-interval diagnostic to all 24 unchanged
targets in `benchmark/m4-cohort-plan-v3.json`, using the exact candidates in
`../tmp/m4-motion-center/cohort-state-v3.json`. It does not replace failed
candidates, rebuild animations, change views, trim clips, or recapture Runtime.

Run with `PYTHONPATH=src;tools`:

```powershell
python tools/m4_local_depth_matrix.py docs/benchmark/m4-cohort-plan-v3.json ../tmp/m4-motion-center/cohort-state-v3.json ../tmp/m4-motion-center/local-depth-matrix-v1 --limit 3
```

Each invocation defaults to three unfinished cells; `--limit 21` completed the
remaining cells in this run. Resume validates the
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
check.

The full run is now complete: 24/24 processed, 17 fully measured, seven with
unmeasured records, zero pending. Across all pair/frame records there are 4,289
unresolved, 631 uniform-front proxy, 247 uniform-back proxy, 1,067 no-overlap and
870 unmeasured results. These counts do not denote independent visual samples.
The frozen evidence is [matrix audit](benchmark/m4-local-depth-matrix-evidence-v1.json).

`tools/m4_local_depth_matrix_audit.py` verifies report hashes, frozen candidate
identities and recalculated counts, and presents reused geometry/contact/Runtime
evidence separately. Empty reports cannot count as fully measured. Run:

```powershell
python tools/m4_local_depth_matrix_audit.py docs/benchmark/m4-cohort-plan-v3.json ../tmp/m4-motion-center/cohort-state-v3.json ../tmp/m4-motion-center/local-depth-matrix-v1 ../tmp/m4-motion-center/local-depth-matrix-v1/audit.json
```

This also writes `audit.html`. Original technical failures remain in force; this
run neither changes meshes nor recaptures Runtime nor grants visual acceptance.
The next algorithm direction is documented in
[side-turn and rotation policy](m4-side-turn-visual-policy.md).

A checkpoint regression test confirms exact results are reused and changed
report bytes or profile identity are rejected before reuse. The batch does not
restart a still-running process on an observation timeout; resume only after the
original process is confirmed terminal.
