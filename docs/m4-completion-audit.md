# M4 delivery audit

The fixed v3 matrix retains eight sources and three character structures, without
replacing failed motions. The current review snapshot is
`../tmp/m4-motion-center/m4-completion-audit-reviews-v1.json`; the operator entry is
`../tmp/m4-motion-center/m4-completion-review-v1.html`.

All 24 jobs completed and contain 11,334 historical official Runtime samples.
This audit does not recapture them. Projection passes 6/24, geometry 11/24,
contact 9/24, depth 0/24, and sampled Runtime comparison 24/24. All candidates
retain technical exceptions. None has a saved external-motion stage decision.
These are separate outcomes, not a claim of 24 supported motions.

The raw v3 state does not include the later depth-completeness fields: the new
report therefore records completeness unknown for all 24. A zero incomplete
counter beside 24 unknown entries must not be read as complete depth evidence.
Earlier enriched snapshots describe their own measurements only.

The centralized review page binds source and target hashes, displays the source
skeleton and actual target player, and reuses the revision/evidence-bound stage
review API. It never turns an automated test into a human decision. Source
category names still require checking against the actual source performance.

Remaining milestone work is to establish the accepted operating range from
these exact candidates, resolve or explicitly expose out-of-range projection,
contact and clothing overlap, and collect stage feedback. Full turns requiring
unseen artwork and unsupported cloth surfaces remain explicit limitations.
Experimental sleeve depth planes are not default repairs: the latest experiment
introduced nine unmeasured samples and remains unadopted.

Validation for this delivery: 21 cohort/report/navigation unit tests and seven
existing synthetic stage-review browser checks pass. The new synthetic cohort
browser test checks seven navigation/save/identity cases without real decisions.
The preceding intake/generation/recovery/review audit passed 37 tests; it is not
a new Kimodo generation or Runtime capture.

Source content now has [dual-view sampled observations](m4-source-category-inspection.md).
In particular, `raise-arms` is a one-arm bent-elbow cheering sample and `walking`
has forward-reaching arms. Coverage claims must use these concrete descriptions;
the original plan and pending category authority are not silently relabeled.

Read-only Chrome verification loaded all eight real source previews, their eight
Alice target player canvases and stage-review forms. No review POST was sent.
This verifies delivery and identity checks, not the visual correctness of the
motions or the other sixteen target players.

## Refreshed diagnostics and explicit breathing feedback

The separate `cohort-diagnostics-refreshed-v1.json` snapshot rereads all 24 exact
candidates through the live API. Sixteen have complete sampled depth checks;
eight have incomplete checks, all Huiye motions. The latter include resource
limits and actual depth conflicts. Completion of sampling is not a depth pass.
This replaces the unknown-completeness interpretation for this new snapshot,
not the historical state or previous experimental reports.

The user explicitly accepted breathing on Alice, Huiye and Hongmeiling with
technical exceptions retained. Each exact candidate now has revision 1 with
`accepted_with_exceptions`, after matching artifact and readiness hashes against
the reviewed snapshot. Other motions are not covered by that decision. The
fresh stage snapshot is `cohort-reviewed-breathing-v1.json`.

## Complete fixed-cohort export verification

All 24 frozen candidates were downloaded through the public workbench endpoint.
Their ZIP inventories and 2,200 total contained files matched the addressed
stored artifacts byte-for-byte. Each candidate's playback, contact and depth
HTML endpoints were readable, and its job/artifact identity was unchanged after
verification. See [per-candidate identities](benchmark/m4-fixed-cohort-delivery-v1.json)
and `../tmp/m4-motion-center/cohort-delivery-v1/summary.json`.

This verifies delivery at the recorded times, not all rendered frames or new
captures. All 24 technical readiness results remain `needs_changes`; the three
explicit breathing acceptances do not override these results. Baseline and
alternative players now expose separate exact-job download links. Six delivery
tests and 20 synthetic browser checks pass. One initial browser startup wait
timed out during the concurrent download run; the diagnostic rerun passed without
changing candidate data. This is not a responsiveness benchmark under load.

## Real Windows generation lifecycle checks

`tests/test_motion_generation_lifecycle.py` exercises the actual manager executor,
progress file, cancellation, Windows process-tree termination and durable result
reader. Only the model command is replaced with a real Python worker that spawns
a real sleeping descendant. A Windows process handle proves the descendant is
alive before cancellation and terminated afterward; the worker also exits.

Both explicit cancellation and graceful manager shutdown pass. A new manager
reads the same canceled outcome; retry creates a new identity with unchanged
generation parameters and preserves the original request and result. These two
integration cases plus six existing generation contract tests pass on Windows
with ordinary process permissions. The initial sandbox run could not terminate
the tree and correctly produced failure instead of claiming successful cancel.

This is lifecycle evidence using a synthetic workload, not a new Kimodo model
run. Abrupt server termination and orphan cleanup are not covered: the current
executor uses taskkill during cleanup, which requires the manager to reach that
cleanup. This remains a recovery-hardening item; durable interrupted status alone
does not prove that descendants of a forcibly terminated service have exited.

### Abrupt-exit hardening

The subsequent implementation adds `motion_process_owner.py`: Windows workers
start suspended, join a verified kill-on-close Job Object, and only then resume.
The service owns the non-inheritable handle. Normal cleanup also closes that job
after a worker exits, covering any remaining descendants. Ownership failures
stop the suspended worker and expose `motion_process_ownership_failed`.

A disposable real manager host now spawns a worker and grandchild. The test opens
handles proving both are alive, kills only the host (no tree-kill command), and
verifies both handles become signaled. A fresh manager reads the old request as
interrupted and retries under a new ID without changing the original bytes.
Two injected startup failure boundaries also prove the worker payload never runs.
All 36 relevant generation, intake, ownership and suspended-thread tests pass.
This closes the preceding running-worker orphan gap for Windows; it does not
claim non-Windows crash containment, GPU model quality or checkpoint resumption.
The already-running workbench must restart to load the new backend implementation.

### Loaded backend and real-input smoke verification

The workbench on port 8918 was restarted at `f0a2be9` after checking the live
motion queue, recent durable job outcomes and actual worker processes. The
replacement service PID at verification was 26228. A broad project-overview
query timed out before restart; this was not treated as evidence of task completion.

Real FBX (299 frames), its verified BVH (299 frames), and external SOMA77 NPZ
(120 frames) compiled successfully under the new ownership launcher. FBX and BVH
produced the same MotionIR bundle; all three public preview payloads matched
their recorded hashes. All 267 pre-restart motion requests, results and stage
decisions remained byte-identical. Exact jobs and hashes are in
[the deployment receipt](benchmark/m4-process-owner-deployment-v1.json).
These are new source compilation runs, not a new Kimodo generation or target
Runtime capture. The previous restart-required note is now satisfied for this
local workbench.
