# Torso projection across frozen characters and sources

This experiment supplements the original eight-motion matrix. It does not
replace failed front-view cases or infer visual acceptance from numeric checks.
The source labels remain filename/prompt categories awaiting visual verification.

## Reproduce

```powershell
$env:PYTHONPATH='src;tools'
python -X utf8 tools/m4_motion_cohort.py docs/benchmark/m4-torso-cohort-plan-v1.json ../tmp/m4-motion-center/torso-cohort-state-v1.json --steps 300
python -X utf8 tools/m4_motion_cohort_report.py docs/benchmark/m4-torso-cohort-plan-v1.json ../tmp/m4-motion-center/torso-cohort-state-v1.json ../tmp/m4-motion-center/torso-cohort-report-v1.html
python -X utf8 tools/m4_torso_source_support.py docs/benchmark/m4-cohort-plan-v3.json ../tmp/m4-motion-center/cohort-state-v3.json ../tmp/m4-motion-center/torso-source-support-v1.json
```

Resume the same state to retain exact task IDs and failures. A live runner holds
the state lock; do not submit a second runner or delete its state. The plan
explicitly requests the torso strategy and its expected execution profile.
Application, geometry, depth completeness and stage readiness are separate fields.
Absent application evidence stays unknown, including on successful tasks.

The torso plan freezes Alice, Huiye and Hongmeiling, with full FBX raise-arms
at -30 degrees and full Kimodo wave at the declared front view. Its plan digest
is `945d457e07eb177481845c9dc456358dc9861caacfc77d7acc45ba2bd6e46144`.
The `parent_plan_sha256` addresses the immediate v3 baseline; the inherited
`baseline_plan` field names its historical v2 baseline. The explicitly recorded
Hongmeiling raise task is reused with its unchanged source, character, projection,
full-clip request and execution profiles. The remaining five tasks are new.

## Cross-character result

All six candidates applied the torso bake and passed geometry, with 3,063
official Runtime frames total (646 for each raise clip, 375 for each wave clip).
This total includes the explicitly reused 646-frame Hongmeiling task; 2,417
frames were newly captured for the other five candidates in this run.
Ankle correction remains reported separately and no contact interval is marked
unmeasured or partial by these candidates' contact checks.

All six still have depth exceptions and aggregate `needs_changes` readiness.
Huiye's two candidates each include 27 unmeasured pair samples. The other four
have complete sampled depth checks, which is not the same as passing depth.
No candidate has been visually accepted. Numeric deformation agreement does not
prove the resulting illustration looks natural. Exact IDs, artifacts and counts
are frozen in `benchmark/m4-torso-cohort-evidence-v1.json`.

The report is `../tmp/m4-motion-center/torso-cohort-report-v1.html`. The Alice
Kimodo candidate's inline readiness and comparison were checked in live Chrome:
comparison returns only the matching-strategy candidate and no recommendation.
An initial browser attempt timed out before locating its button; a fresh page
showed the candidate and the repeated check passed. No root cause or UI fix is
claimed from that transient timeout. Twenty-five focused regression tests pass.

## Full-source support scan

The original front-view eight-source plan was measured without trimming frames,
switching views or changing thresholds. Verified source bundle identities and
every measured frame are saved in `torso-source-support-v1.json`.

| Source label | Frames | Outside torso shape bounds |
| --- | ---: | ---: |
| Breathing | 299 | 0 |
| Walking | 122 | 40 |
| Raise arms | 58 | 0 |
| Turn | 44 | 31 |
| Squat | 57 | 0 |
| Boxing | 67 | 0 |
| Reach | 121 | 0 |
| Kimodo wave | 120 | 0 |

Walking exceeds the shear bound in 40 frames. Turning includes 27 back-facing,
four side-degenerate and four width-limit observations; reason counts overlap
within the 31 unsupported frames. Six clips being within source bounds does not
mean their limb projection, geometry, contact or visual output passes.

The current model narrows and shears a torso plane while preserving head and arm
shape. It cannot reconstruct side/back artwork. Full turns therefore remain an
explicit unsupported case for this single-view bake. See
[rotation diagnostics](m4-rotation-diagnostics.md) for the separate distinction
between angle branch crossings, genuine winding and unobserved axial twist.
