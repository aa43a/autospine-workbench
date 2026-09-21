# Regional depth worker integration

## Conservative sparse regional sampling experiment

`m4_regional_source_check.py --sparse` now carries the existing conservative
triangle-box sparse tile policy through refinement, garment constraints, limb
constraints and ordering. All probes sharing overlap results must use the same
policy. Default worker behavior stays unchanged; raster pixel precision, alpha
threshold, depth margin and 64-million-pixel pair budget are unchanged.

On the exact fixed Huiye wave source job
`motion-883cb61bb3a84aee91f233cca536a552`, dense and sparse replays retain all
432 recorded checks. The 238 previously measured outcomes match exactly by
status, overlap count and depth-class counts. Sparse evaluation recovers 39
checks; unmeasured count falls from 194 to 155. Both retain 120 order blockers,
emit no replacement skeleton and do not trigger Runtime capture or adoption.

Evidence under `../tmp/m4-motion-center/`:
`regional-kimodo-huiye-dense-v1/report.json`,
`regional-kimodo-huiye-sparse-v1/report.json`, and
`regional-kimodo-huiye-sparse-comparison-v1.json`.
Dense SHA256: `7ccda81d4936d68ac5894d77587abe98062d17e0e81239673f68ba666f3bfdbf`;
sparse SHA256: `e920b9e3645ee6082a9a63edfb486278d8ef9fcde73be6fb27b7ce10e7ead064`.
The comparison tool rejects changed source identities, missing sample keys and
changed previously measured outcomes. Twenty-eight focused tests pass, including
cache-policy propagation and conservative sparse-vs-dense overlap equivalence.

## Live SOMA77 delivery verification (2026-09-21)

The server was restarted after checking its listener identity and unfinished
jobs. `m4-regional-kimodo-plan-v1.json` preserves the three frozen characters and
the original generated wave bytes, with regional strategy explicitly selected.
Plan identity: `9c244540c8457a60ab84f4d146510ba5b73332157d8a077d7d818c466e09afb5`.
This is an additional experiment, not replacement of the 24-cell baseline.

| Character | New API job | Fresh Runtime frames | Download files | Unmeasured | Order failures |
| --- | --- | ---: | ---: | ---: | ---: |
| Alice | motion-2d475d4ac87344aab4fc2b18c3b04cf1 | 375 | 97 | 0 | 120 |
| Huiye | motion-13aa3123eb17439e8dfdde4361ce32e4 | 375 | 87 | 194 | 120 |
| Hongmeiling | motion-ad427fb6a0344efe902f2e962f899ebb | 375 | 91 | 0 | 120 |

All three geometry checks pass. Every ordering failure is
`visible_depth_straddle`; all remain `needs_changes` and retain fallback order.
Each actual downloaded ZIP matches the verified immutable artifact file inventory
and every file's bytes. Player, contact and depth HTTP endpoints return HTML;
this is not a browser-render or human visual acceptance claim.

Evidence is in `../tmp/m4-motion-center/regional-kimodo-state-v1.json`,
`regional-kimodo-report-v1.html`, and `regional-kimodo-*-delivery-v1.json`.
The reusable `m4_motion_delivery_check.py JOB OUTPUT` rejects nonterminal jobs,
changed artifact identities, duplicate/missing/extra ZIP files and changed bytes.
Twenty-eight focused tests pass. M4 still requires unresolved quality work;
successful delivery and Runtime correspondence do not establish supported motion.

### Wave exception localization

The 120 ordering failures per character are first-blocker records from a
short-circuiting solver, not 120 independently observed visual defects or an
exhaustive inventory of all overlapping pairs. Model evidence attributes Alice
and Hongmeiling's recorded blockers to interval-margin uncertainty; Huiye's
recorded blockers lack depth support for part of the sleeve pixels.

Operator diagnostics now also collect unmeasured refinement, garment and limb
checks at their own sample times, deduplicating only identical time/reason/pair
records. Huiye's actual wave report consequently exposes 194 pixel-budget limits
alongside 120 order blockers. The first limit is at 0.750 seconds for
`layer-002-component-0000` / `layer-005`; interval midpoint times remain exact.
These details were previously absent from the operator list even though the
aggregate unmeasured count existed. Fifteen focused tests pass; stored candidate
bytes, thresholds, rendering and stage acceptance remain unchanged.

The readiness gate now independently checks refinement sample statuses and each
present cloth/limb unmeasured count, rather than trusting the zero aggregate.
Missing/malformed details and unknown measurement statuses stay unmeasured;
measured uncertainty remains distinct and is subject to the order solver.
Absent optional cloth/limb reports remain valid when that model was inapplicable.
The 2026-09-21 read-only audit of `regional-breathing-state-v2.json` preserves
all three needs-changes results: Alice has 69 unmeasured samples, Huiye 2,613,
and Hongmeiling zero but unresolved ordering conflicts. This audit reads verified
stored artifacts; it does not recapture Runtime or grant visual acceptance.

The optional `external-regional-depth-order-v1` worker profile composes render
partitioning, torso-plane interval refinement, garment/limb constraints, tiled
alpha checks, and guarded ordering. Existing submission defaults are unchanged.
The motion-center target controls expose an optional regional-depth checkbox for
FBX/BVH and verified Kimodo SOMA77 NPZ sources; source changes reset it. The API validates
the explicit profile and records it in the immutable request. Retry preserves
that profile instead of silently returning to the current default.

Partition selection comes from the exact character's existing
`fixed-waist-three-chain-sway-v1` skirt-trial records, not character names or
layer-name guesses. Unknown provenance leaves the slot inventory unchanged.
SOMA77 source sampling uses the same validated NPZ/FK contract as local depth
diagnostics. Regional `source_sampling` records raw/source/array identities and
the explicit `linear_observed_positions` midpoint model. It does not invent BVH
rotation channels or claim measured cloth depth between source frames. Render
partition reconstruction receives the original NPZ and mapping as well.

`tools/m4_regional_source_check.py JOB OUTPUT` replays this strategy on an exact
existing candidate, verifies source identity, rejects already warped torso
geometry, and writes an independent report. It never overwrites an output or
publishes a replacement candidate. Runtime and visual acceptance remain separate.

Actual SOMA77 replay: fixed Alice wave job
`motion-76e0d141f979430db88de1183c46a79b`, artifact
`9fc3e02e74036b34322480c4936f5bfd874c8931bf11372e8c1c19fe2e0c486a`.
`../tmp/m4-motion-center/regional-kimodo-alice-v1/report.json` has SHA256
`9e39540e0288e6636650ee4649554f825847fa45b57d3505e821a2babc768aab`.
All requested checks complete (zero unmeasured), but 120
`visible_depth_straddle` records prevent selection. No replacement skeleton,
new Runtime capture or visual acceptance is claimed. Twenty-five focused tests
cover NPZ corruption, midpoint observations, partition source propagation,
legacy BVH behavior, worker references, incomplete gates and transform identity.

Accepted transformations carry an exact source/candidate digest contract. Setup
vertices follow the source-to-region mapping; geometry and Runtime references
are rebuilt against the resulting slot inventory. Original texture and atlas
bytes remain unchanged. Unmeasured regional checks prevent selection. Failed
ordering retains the original document and produces diagnostics for review.

The regional readiness branch requires matching transform evidence, completed
checks, and successful selected ordering. The legacy readiness output and saved
review identities remain unchanged. Regional constraint rows are supported by
the time-addressed report renderer.

## Real worker evidence

`../tmp/m4-motion-center/regional-worker-hong-v1` records a complete isolated run
using Hong's existing raise-arm motion at -30 degrees. Artifact:
`d245239249bd462aafbf015e94c5d9041f1f26593b96ffd2a6a30b5e6642d9cf`.
All regional checks completed, but 14 visible-straddle records prevented
selection. Unlike the previous fixed torso-depth experiment, this profile uses
the moving torso plane; the two models must not be conflated.

The retained skeleton is byte-identical to the original motion candidate, as
are its texture/atlas bytes. Geometry passed. Official Runtime checked 646 frames
and 27 slots with maximum vertex error 0.00011744571093256878 px. The depth gate
remains `needs_changes`. This verifies the real worker's rejected-order path,
not the selected regional candidate's full worker capture or visual acceptance.

## Workbench submission verification

Formal API task `motion-71e9441a4dbc41f6b4734e01228e2919` completed with artifact
`4152d6356ac06b02757bf5353a030319e9ee9f5864e23d267b30ea6201aafbed`.
It uses the explicit -30 degree projection without the earlier automatic-view
selection receipt, so its artifact identity is independent. Geometry passed;
14 depth-conflict records remain and the original order is retained.

Twenty focused tests cover strategy validation, persisted submission, retry,
worker/profile evidence and comparison. Real Chrome checks cover checkbox
accessibility, source reset, NPZ exclusion, and the completed task's inline
category filters/time links. Task completion does not imply depth acceptance.

## Three-structure supplemental run

`benchmark/m4-regional-breathing-plan-v1.json` preserves all three frozen
characters and the baseline's complete breathing source. It explicitly requests
the regional profile and requires matching output evidence. It is an additional
three-cell regression, not a replacement for the 24-cell baseline. The runner
now supports explicit depth strategy requests with matching expected profiles;
uncertain submissions and terminal failures retain the existing rules.

Resume the same live run, after checking its process has ended, with:

```powershell
python -X utf8 -u tools/m4_motion_cohort.py docs/benchmark/m4-regional-breathing-plan-v1.json ../tmp/m4-motion-center/regional-breathing-state-v1.json --steps 200
```

The regional worker reports partitioning, torso refinement, cloth constraints,
limb constraints, and ordering as distinct progress stages. These callbacks do
not alter generated evidence. Twenty focused runner/profile/worker/progress
tests pass. The first run subsequently ended: Alice completed; Huiye and Hong
failed with `motion_progress_invalid`. The added progress stages had not been
registered with the process transport. Those two failures are plumbing failures,
not character quality conclusions, and remain in the v1 journal.

The transport allowlist is now updated, with a real temporary-file write/read
test and an unknown-step rejection check. Fifteen intake/worker/progress tests
pass with process-tree permissions. Independent v2 plan/state files retain
Alice's unchanged exact candidate and submit new Huiye/Hong tasks after the fix.
Use `m4-regional-breathing-plan-v2.json` and `regional-breathing-state-v2.json` to
resume that run. The v2 run is now terminal: all three candidates completed,
with 3,324 Runtime frames and three geometry passes. All retain depth exceptions;
none is stage-review-ready. Alice and Huiye have incomplete depth checks; Hong's
sampling completed but did not pass the depth gate. This does not establish that
all reported model conflicts are visible rendering errors.

The cohort collector reads exact-artifact depth-status evidence. Reports now
separate never-evaluated depth, incomplete checks, and unknown completeness.
The refreshed v2 report has two incomplete cells and zero unknown-completeness
cells. Existing captures were reused; this refresh did not recapture animation.

Candidate readiness panels now explain next actions and offer same-page view
comparison for projection, geometry, and depth exceptions. Guidance is separate
from immutable review evidence, and stale readiness responses are rejected.
Twelve cohort tests pass; Chrome checks cover same-page comparison and polling
with stale-response rejection. No visual acceptance has been inferred.

## Model uncertainty explanation

Alice's candidate `53cb8bb55f666badb1f0c78d78f024284243dd2589c0c72198533cb71c3e22c1`
retains 299 order-failure records and 69 unmeasured regional checks. For the first
failure, all 1,785 overlap pixels have ambiguous model intervals, with no definite
front/back support. All first 100 displayed records have this uncertainty class;
this is not a claim that all 299 records or the rendered clip are visually wrong.

Inline diagnostics now attach the exact pair/time model counts, distinguishing
margin uncertainty, opposing model support, missing depth, and inconsistent
evidence. They leave the quality gate and stage-review identities unchanged.
Twelve focused diagnostics/progress/gate tests and a real Chrome check pass.
