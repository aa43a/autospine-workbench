# Eye neighborhood binding and whole-character rebuild

## Scope

The v6 policy adds a bounded static-head rule for eyelash pixels in a visible
eye neighborhood. It requires reviewed head/neck anchors, already bound face
and both eye-white layers, same-eye contact, separation from the opposite eye,
face bounds, and limited reference size. Other failed checks and existing
decisions remain unchanged. This is not an expression rig or calibrated accuracy
claim. Decisions remain reversible and grant no publication authority.

On the current Lingxian input, only `layer-018` became newly eligible: all 549
visible pixels pass the bounded neighborhood checks. Alice and Lumia gained no
new eligible rows; their preserved decisions were compared unchanged.

Applied decision:
`61c6f551634bddf65e090c45c28832d41007816b78421e3281c9fd0fc6369901`.

## Actual workbench result

- Project: `lingxian`.
- Job: `job-7d1ae9502d12430892cc74a7965e709e`.
- Bundle: `af783dde52973a1c98f42968b26ecb52d0a82f0a67429d1831e11e368a0b2ef8`.
- Motions: idle, limb-flex-15, wave-left, walk.
- Official Runtime: 1,028 sampled frames, zero geometry failure records.
- Scope: all attachment vertices and nonempty, unclipped framebuffer;
  contact status remains `not_evaluated`.
- Four weighted source layers are covered by supported stage defaults v2;
  the actual weighted-review endpoint reports all four as confirmed by policy.
- Existing human exclusion of `layer-003-residual` was reused from review
  `fa094100ae3ce829a16939b554403b6869ac064bb0b487fd9a9e04ee80f99b61`.

The final-exclusion replay now delegates unrelated binding edits to the existing
strict per-region proof. Source semantics, skeleton, region attachment and
texture must remain consistent. It preserves the original human decision and
explicitly records that no new human confirmation occurred. Other source
changes continue to fail closed.

The walk frame at sample 64 was inspected: the character is present without an
obvious whole-image offset. Small specks remain around the outer hair edge.
The user accepted the whole-character stage, including the prompted inspection
of those specks. Receipt:
`46418cc641268a83df686bdc8fc18e0abe4be73b227ecc25e83bfe390c8a6bc6`.
All four visual aspects are acceptable for this exact candidate. Review time
was not measured. This is stage acceptance, not publication authorization.

## Verification

- 27 Python policy, HTTP, replay and quality tests passed.
- 20 Python final-exclusion/replay and quality tests passed after the proof guard.
- 597 Web tests passed.
- Actual v6 proposals and the saved v6 decision passed schema validation.
- Historical v1-v5 schemas and decision readers remain supported.

The first-ten v10 report remains a historical snapshot with four accepted
characters. A fresh full-cohort read in v11 verifies five accepted characters,
nine measured candidates and 27 of 30 required motion cases passed. There are
102 eligible automatic bindings, none independently assessed; error rate and
human review time remain unmeasured.
