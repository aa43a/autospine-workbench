# Boxing: temporal correction and projection prerequisite

2026-09-28. This supersedes the next-action inference in the previous interval probe; it does not overwrite that experiment or any candidate review.

## Temporal experiment

The independent repair's three failing intervals show about 15.6–18.3 px maximum vertex displacement across approximately 1 ms, versus 2.6–5.2 px in the exact parent. Relevant bone transform determinants remain approximately one, excluding a singular inverse transform at those samples.

An opt-in initial guess now transports the prior local correction through the current bone transforms and decays it at 20/s. The solver retains the existing displacement budget and pins all fixed vertices. The experiment is `E:/proj/unusual/localset/tmp/m4-boxing-temporal-repair-v1/`.

Four rounds, 330 knots and 659 checks still fail at 0.411962891, 0.549462891 and 0.599121094 seconds. Minimum area ratios are approximately −0.04602, −0.11389 and −0.07834. Maximum displacement is 13.0799 px, maximum fixed-vertex displacement zero. The discontinuities move but are not removed. The candidate is not adopted and has no new Runtime/visual pass.

## More fundamental prerequisite

Inspection of `motion_target_worker.build_candidate` and `motion_clip.selected_ratios` confirms that the exact Hongmeiling boxing parent failed `character_length_projection_collapsed`. The worker intentionally retained a rotation-only diagnostic animation after the projected-length calculation raised. The unit determinants agree with that diagnostic fallback; they do not prove successful 3D-to-2D length adaptation.

Thus fixing the fallback mesh alone cannot establish supported boxing motion. Further automatic repair should not silently proceed as if projection had succeeded. The standalone interval tool now rejects parents with projection issues unless `--diagnostic-fallback` is explicitly provided; its report preserves those inherited issues even under that experimental override. It never changes adoption authority.

## Validation and direction

17 existing/new tests covering parent repair, warm-start transport, additive repair and area projection passed before the prerequisite guard; its additional regression verifies rejection before artifact access or output creation. The seed regression checks fixed vertices, budget and input immutability.

Do not continue merely densifying this rotation-only fallback. The next adaptation must explicitly address an observable projected pose/length representation or a declared artwork/depth alternative, retaining source uncertainty and then re-running whole-character checks. This finding leaves boxing unsupported under the current full-clip strategy, not M4 complete and not all possible boxing sources unsupported.
