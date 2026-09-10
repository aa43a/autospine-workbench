# R3-S acceptance audit — 2026-09-10

The four original sleeves now have candidate export and sampled Runtime evidence;
the additional Bayunlan pair also passes the ordinary repair/export workflow.
This is not authorization to publish, nor a claim about arbitrary motions.

| Requirement | Inspected evidence | Result |
|---|---|---|
| Reviewed sleeve/hand/cuff/drape source | Source-linked original drafts; Bayunlan six explicit edits, three unknowns retained | Preserved |
| Four original multi-contact structures | Huiye interface edges 8/7; Uuz 8/8; seven tracks per sleeve | Present |
| Setup ≤1e-7 px, weight sum error ≤1e-9 | Original final cuff artifacts: maximum setup 2.543e-13 px; weight error zero | Pass |
| Fixed interfaces | Four original anchor displacement values zero | Pass |
| Forearm ±30°, hand ±30°, drape ±10° and declared synchronized combinations | Seven tracks, all original dense QA samples rechecked with production `passed` predicate | Pass within sampled profile |
| Target and official Runtime | Original four: 7,196 frames, 1,153,159 contact probes; Bayunlan: 3,598 frames, 345,408 probes | No sampled contact failures |
| Normal entry, no manual SHA | Ordinary workflow `run-8bd79d59fbf8a2f62b19e24908f9c87d7bf17549b684f713c3906e86f891d59d` completed 14 stages | Both candidates exported |
| Fail-closed behavior | Retained historical negative artifacts; web-job/target tests and blocked terminal Schema test | Preserved |
| Reversible candidates | Commit 3965233; withdrawal/restore tests validate current sources and ZIP bytes | Pass |
| Historical evidence and maintainability | Original four pass through new repair byte-identically; source-size checks pass | Preserved |
| Shown connection/overlap quality | User explicitly accepted displayed six-sleeve views | Accepted only for shown evidence |
| Untuned independent sleeve validation before broader generality claim | Bayunlan informed budget-allocation diagnosis; it is no longer an untouched holdout | Not proven |

Original cuff addresses:
Huiye `d64ef03bc0fcc6f1134a59dcd81d703e149317e8639bdf86460935b7ef5e91be`;
Uuz `a08b538161dd1d5e884502bf5adfc5ec4fc57370fe5c02fa06d9d321b90857ee`.
Detailed Runtime run locations and limits remain in `milestone-r3s-sleeves.md`
and `r3s-budget-headroom.md`.

The human observation is sealed at
`tmp/r3s-visual-review-2026-09-10/3b4c024624b911b3d0dd700a6af7c7eaa2c827cd082a1d51c81c2cb809597f22.json`.
It binds six capture digests and their asset hashes to the exact response:
“所展示的连接与重叠可以接受”. It excludes unseen frames, arbitrary motions,
whole-character approval and publication. Existing immutable workflow reports
remain `needs_review`; this external observation does not rewrite their authority.

Follow-up remains: freeze the current policy and test an additional reviewed sleeve
case without tuning against it before expanding generality claims. Full-character
motion/occlusion integration is not established by isolated sleeve capture.

Main workbench review links are now verified end-to-end; see
`r3s-workbench-review-entry.md`. The attempted Yaomeng sample was rejected by
the user as sleeveless and retained only as a negative applicability observation.
It does not satisfy the additional sleeve validation requirement.
