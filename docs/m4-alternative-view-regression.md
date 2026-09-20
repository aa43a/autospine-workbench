# M4 alternative-view regression

The frozen front matrix remains `benchmark/m4-cohort-plan-v3.json`. Source
selection does not alter it or inherit visual acceptance from another candidate.

`tools/m4_prepare_views.py` compares complete source clips through the public API,
preserves a passing current view, and submits a different view only with its exact
comparison receipt. Interrupted requests retain a submission marker. Only an
explicit queue-full rejection can be retried without reconciling the request.
An independent lock and stop marker support resuming exact source task IDs.

The actual eight-source run produced:

| Sources | Result |
| --- | --- |
| Breathing, Kimodo wave | Keep front |
| Walking, raise arms, squat, reach | Compiled independent side versions |
| Turn, boxing | Neither available projection passes; retain exceptions |

`tools/m4_view_cohort_plan.py` freezes the four changed sources against the same
three character artifacts. `benchmark/m4-alternative-view-plan-v1.json` records
original task IDs, comparison hashes, prepared motion identities, and the baseline
digest. The resulting twelve target cases still need geometry, support, depth,
official Runtime and stage visual checks. Source qualification is not evidence
that a front drawing becomes a valid side drawing.

Run this matrix after the current front runner releases the shared task queue:

```powershell
python tools/m4_motion_cohort.py docs/benchmark/m4-alternative-view-plan-v1.json ../tmp/m4-motion-center/alternative-view-state-v1.json --steps 1000
```

## Next visual adaptation work

The user accepts modest motion as a direction and requests better side-turn and
full-rotation handling. This is not candidate-specific visual acceptance.

1. Diagnose angle branch jumps, near-zero projected limbs, actual winding and
   longitudinal twist separately. Existing unwrap alone cannot distinguish them.
2. Add oblique projection candidates with whole-clip stability and artwork limits;
   avoid frame-by-frame camera switching that destroys contact continuity.
3. Add bounded torso/shoulder/hip deformation and explicit near/far ownership.
   Missing side/back art remains an exception, not an inferred successful repair.
4. Compare original and adapted motion on the same timeline, including between-key
   samples, contacts, seams, triangle orientation and rendered occlusion.

These are pending implementation; the current source-view runner does not perform
2.5D artwork deformation, fix rotation singularities or authorize production.
