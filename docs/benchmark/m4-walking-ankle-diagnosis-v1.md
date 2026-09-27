# Side walking: bounded ankle failure diagnosis

2026-09-27. Candidate `motion-06ec02183a644786a2ac435633d572ce`, artifact
`c535f0ce650a4d9eafa7bcb82e06bedb4a37850f67466789b5825870724435f1`.

The build completed, but moving-ankle correction was not applied. The retained
animation passed 753 Runtime geometry samples; this does not validate the failed
correction. Contact and depth exceptions remain.

The first solver failure is at 0.063020828125 seconds. The endpoint threshold is
5.493700613 px; errors are 6.168450439 and 6.284324251 px. The previous solution
at 0.04726562109375 seconds has right calf correction +1.764441488 degrees.

`tools/m4_moving_ankle_failure_probe.py` verifies the exact original skeleton
identity before comparing three solves against the same target points:

| Constraints | Maximum endpoint error | Result |
| --- | ---: | --- |
| Original root and correction angular speed limits | 6.284324251 px | No bounded solution found |
| Root continuity, no angular speed constraint | 0.000017043 px | Single-frame candidate |
| Independent frame, same spatial bounds | 0.000018150 px | Single-frame candidate |

The root-continuous alternative uses right calf correction +24.566851791 degrees,
over 22 degrees from the previous solution within 0.015755207 seconds. It must
not be adopted as a timeline: removing the speed bound would introduce a jump.
This demonstrates spatial reachability at this frame, not feasibility of the
whole motion under continuity limits or proof of global infeasibility.

Next implementation direction: solve a temporal window with alternative knee
branches and unchanged endpoint, root displacement, angular displacement and
continuity checks. A local greedy trajectory can select a branch that cannot
continue. Determine whether a continuous bounded path exists before changing
any limits. Keep failed inputs and never publish a partial corrected animation.

Receipt: `E:/proj/unusual/localset/tmp/m4-walking-ankle-failure-probe-v1.json`.
No candidate, source animation, production threshold, or human decision was
modified by the probe.

## Joint window experiment

`ankle_window_solver.py` jointly searches the first six knots, trying neutral
and opposite knee seeds. The initial correction remains zero. Root displacement
15%, correction rotation 30 degrees, root speed 2 reference lengths/second,
correction angular speed 180 degrees/second, and endpoint error 1% stay unchanged.
The optimizer uses numerical headroom and independent post-solve inequalities.

The real source now admits a knot-level path with peak endpoint error
5.488179345 px. Reconstructing the animation and checking full affine FK at
knots and midpoints (11 times) finds 5.591680460 px at 0.055143224609375 seconds,
right foot, above 5.493700613 px. This path is therefore **not adopted**.
The next step must constrain interpolation samples, then extend beyond this
initial window; the short window is not evidence of whole-walk support.

Receipt: `E:/proj/unusual/localset/tmp/m4-walking-ankle-window-probe-v1.json`.
19 focused tests pass, including independent FK, continuity bounds, immutable
inputs, invalid windows and unreachable-window rejection. No production route
uses the experimental solver yet.
