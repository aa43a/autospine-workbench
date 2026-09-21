# Regional depth worker integration

The optional `external-regional-depth-order-v1` worker profile composes render
partitioning, torso-plane interval refinement, garment/limb constraints, tiled
alpha checks, and guarded ordering. Existing submission defaults are unchanged.
The motion-center target controls expose an optional regional-depth checkbox for
FBX/BVH sources; source changes reset it and NPZ disables it. The API validates
the explicit profile and records it in the immutable request. Retry preserves
that profile instead of silently returning to the current default.

Partition selection comes from the exact character's existing
`fixed-waist-three-chain-sway-v1` skirt-trial records, not character names or
layer-name guesses. Unknown provenance leaves the slot inventory unchanged.
SOMA77 source sampling is not supported by this new regional profile yet; the
existing Kimodo retarget profile remains available.

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
tests pass. This supplemental run is still in progress; no outcomes are inferred.
