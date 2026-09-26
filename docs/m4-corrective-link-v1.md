# M4 corrective candidate linkage

2026-09-26. This delivery prepares isolated deform corrections for the existing
motion-center related-candidate comparison, without replacing the baseline.

## Contract

`tools/m4_register_corrective_candidate.py` defaults to proof-only operation.
It reads immutable bundles and checks the original request, character and motion
identity, unchanged manifest, textures, bone tracks and all unselected content.
Only deform tracks on explicitly named slots may differ. Final numeric samples
must include the source grid, animation keys and interval midpoints. The existing
related-evidence verifier checks that Runtime results cover that exact final grid.
Historical reports without a partial-batch flag require the same actual coverage.

The related-evidence reader accepts both existing ancestor provenance and the
motion builder's exact input-character bundle identity, while requiring identical
source-address records. Existing valid evidence remains unchanged.

## Real candidate checked

- Baseline: `motion-3954d8fe062b4a439b26a90667e97781` (Alice Squat).
- Corrective bundle: `418038c3621a71b2a56893f53862b0611ce1feb7e0b232f75e786d09ff29dcb2`.
- Changed deform slots: `layer-001-l`, `layer-001-r`, `layer-005`.
- 3,713 existing Runtime samples verified; this delivery did not recapture them.
- Capturing Runtime: 4.3.13. Export target: Spine 4.3.26.
- Local receipt: `tmp/m4-corrective-link-v1/proof.json`.

Registration initially waited for the service update. On 2026-09-26, after
confirming the old service process had exited and port 8918 had no listener,
the original `tools/start-local-workbench.ps1` was approved and started on 8918.
The original Squat job returned `succeeded` from the updated service.
The tool's `--register` option then appended registration
`470828748c0df1bd32d13c034319de10cc30cfd138b8837d28d65e7731e95392`.
The saved receipt is `tmp/m4-corrective-link-v1/registered.json`.
It does not select the candidate or inherit visual acceptance from the baseline.

## Remaining work

Contact, depth/occlusion and visual checks remain pending. The inspected images
still show shoulder-side scattered pixels and a leg region exposed beside the
skirt. These are not resolved by successful linkage or sampled geometry checks.
The removed shoulder-coverage constraint must not be reinstated to hide them.
M4's three-character/eight-motion scope is unchanged.

## Verification

`test_corrective_candidate_link`, `test_motion_related_evidence`, and
`test_motion_related_candidates` cover complete versus partial sampling,
request changes, unrelated bone/texture changes, provenance and registry behavior.

## Portable export follow-up

Related downloads now include every immutable candidate file, including numeric
reference chunks, geometry and corrective provenance, plus the original receipt.
`related-export.json` lists candidate and evidence file hashes separately, so the
original bundle identity can be reconstructed without treating added export
metadata as part of that bundle. Entries are compressed and retain fixed ZIP
timestamps. No acceptance or production authorization is introduced.

The real Alice Squat export restored all 124 candidate files byte-for-byte and
reconstructed the same bundle digest. This uses saved job and Runtime records:
the live 8918 connection was refused during the initial export check. Online
download remains unverified. The 13 related-candidate tests pass.

After service recovery, Browser Use refused navigation because saved browser
permissions could not be verified. No alternate browser control or indirect UI
workaround was used. Playback, timeline interaction, and the live download still
need browser verification; successful registration does not prove these checks.
