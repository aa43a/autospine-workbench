# Regional depth worker integration

The optional `external-regional-depth-order-v1` worker profile composes render
partitioning, torso-plane interval refinement, garment/limb constraints, tiled
alpha checks, and guarded ordering. Existing submission defaults are unchanged;
the profile is not yet exposed through the workbench submission UI.

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
