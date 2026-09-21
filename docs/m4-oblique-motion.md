# Constant-yaw MotionIR candidates

`oblique_source.py` extracts world-space vectors and root positions from verified
BVH or validated SOMA77 inputs, expressed in the original declared camera basis.
`oblique_motion.py` applies a constant orthogonal yaw, recomputes projected
directions, parent-relative setup deltas and root translation together. It produces
an independent MotionIR and receipt; existing axis-only mapping formats and frozen
bundles are unchanged. The receipt identifies parent motion, spatial inputs, yaw,
precision and result. BVH uses 12 decimals and Kimodo preserves its 5-decimal
compiler precision. Degenerate projections fail explicitly.

Actual frozen eight-source tests compiled thirteen angles from -90 to +90 degrees
at 15-degree intervals. Zero-degree tracks reproduced the existing source transfer
within 1e-9 (the check stops the run otherwise). Smallest absolute qualifying yaws:

| Source | Yaw passing existing full-clip projection checks |
| --- | --- |
| Breathing | 0 |
| Walking | -45 |
| Raise arms | -30 (+30 also passes) |
| Turn | None |
| Squat | -60 (+60 also passes) |
| Boxing | None |
| Reach | +45 |
| Kimodo wave | 0 |

Selection here only minimizes deviation from the original view among angles that
pass the existing visibility and relative-length tests. It is not an aesthetic
score or an automatic target acceptance policy. Negative and positive yaws can
have different results because source poses and source artwork are asymmetric.

Reproduce with `tools/m4_oblique_candidates.py` and the frozen v3 plan; generated
MotionIR documents, receipts and summary are under
`../tmp/m4-motion-center/oblique-source-v1/`.

## Workbench target integration

Target requests now accept an explicit `projection` with profile
`constant-yaw-source-motion-v1` and `yaw_degrees` in [-90,90]. Omission retains the
existing behavior. Retry preserves this selection. The motion center exposes a
constant relative yaw selector only when the server advertises support; choosing
a different source resets it. No source or reviewed character artifact is replaced.

The worker compiles independent MotionIR, derives axial length ratios from the
same projection receipt, and recomputes source depth using the same yaw. Original
world-space source contact eligibility remains unchanged by camera yaw; target
support correction and geometry are evaluated again on the new candidate. The
receipt is part of the verified output inventory as `motion-projection.json`.

First actual target: Alice walking at -45 degrees,
`motion-650a3b14b51b49ec93638451f8474fee`, artifact
`6088dbcb780444e8a164a1d7dae15302ee55ba75abf2bcb6ba68b51ae475e2b7`.
It completed 377 official Runtime frames with geometry passing. Contact remains
`inferred_proxy_drift` and depth remains `depth_candidates_need_review`; this is
not an accepted motion. The independent side-view cohort continues separately.

Validation: 29 related backend tests and browser checks for explicit selection,
source-change reset and omitted-projection compatibility. No side/back texture
reconstruction or torso mesh deformation is implemented here. Current capture
and source projection success do not imply that front artwork looks correct
under every oblique motion.

## Automatic source-angle proposal

The motion center's **自动选择投影角度** compares all thirteen constant yaws
against the entire verified source. It retains zero when qualified, otherwise
chooses the smallest absolute qualified angle (negative first for equal angles).
No qualifying angle produces an explicit exception, not an approved fallback.
This is a source projection rule, not an aesthetic or target acceptance score.

The comparison receipt binds the source job, source bytes and MotionIR identity.
Submission recomputes the comparison and rejects changed receipts or mismatched
angles. The selected receipt travels into the candidate's projection artifact;
retry revalidates it. Changing source or manually choosing an angle clears the
automatic selection. Late responses cannot overwrite a newer selection.

GET `/api/motions/{job_id}/compare-oblique` is read-only. Automatic submissions
include `projection_selection: {comparison_sha256: ...}` alongside `projection`.
Geometry, contact, depth and Runtime checks still run on the resulting character.

The workbench now defaults **新动作默认自动选择合格投影** to enabled. Selecting
a compiled source starts the same verified thirteen-angle comparison; merely
refreshing or reselecting the same source does not repeat it. Target submission
is disabled while the comparison is pending. Manual yaw changes opt out for the
current page session, while the operator can explicitly re-enable the checkbox
or comparison button. Source changes clear the previous angle and receipt.
Late replies cannot overwrite a newer source or manual decision. Failed or
unqualified comparisons display an exception and do not claim a recommended
fallback; the unchanged source can still be built as a diagnostic candidate.
This changes the default UI selection, not historical jobs or the backend
recommendation/acceptance rules.

Live GET-only Chrome checks verified walking selects -45 degrees, generated
Kimodo wave selects 0 degrees, and manual selection disables automatic changes.
No real jobs were created by this test. Fourteen synthetic browser cases and
17 projection/intake backend tests pass, including cancellation of a pending
comparison and explicit re-enable.

Validation: source comparison, stale receipt and mismatched angle unit checks,
real BVH HTTP comparison, and browser payload/manual override/source reset checks.
Comparison in progress disables target submission, including programmatic button
activation; a manual override or source change ends that pending selection.

Real automatic-path validation: Hongmeiling raise-arms chose -30 degrees and
created `motion-6d7be7b37ac141c1906cf28ca5eb4c74`, artifact
`1842fe3961713e9c7b32f3463be804749b7268208f1540a52a2c91053379434f`.
Its 646 Runtime frames passed geometry and current inferred support checks;
depth remains `depth_candidates_need_review`. The verified projection artifact
contains the exact automatic comparison digest and source job. It is readable
through `view/motion-projection.json` and the target card's projection link.
This verifies persistence and execution, not human visual acceptance.

## Frozen oblique target cohort

`tools/m4_oblique_cohort_plan.py` binds the full source-angle summary to the v3
baseline and emits `benchmark/m4-oblique-cohort-plan-v1.json`. Four nonzero
qualified angles are tested on all three unchanged characters (12 cases).
Unavailable projections and unchanged zero-degree sources remain listed rather
than disappearing from the scope. These twelve cases supplement the original
eight-category matrix; they do not replace its failed cases.

The cohort runner submits each exact projection and checks the returned projection
before accepting a completed task as evidence. The already completed Alice -45
walking job is reused after checking its immutable request, character identity
and result; the other cases are new tasks. State:
`../tmp/m4-motion-center/oblique-cohort-state-v1.json`.

The initial Alice contact failure is at 3.576431996 seconds: endpoint residual
4.109350732 pixels, after the left calf correction reaches its 30-degree bound.
The existing root/rotation limits and 1% residual gate remain unchanged. This
does not prove no solution exists globally; it explains why this bounded causal
attempt was rejected. New views must be evaluated, not approved from source
projection alone.
