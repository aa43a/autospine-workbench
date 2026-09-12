# Hard-constrained direction fit: single-pose trial

The direction fit now has a separate experimental solver that minimizes target error while imposing area ratio 0.5–2, edge stretch at most 2, and cloth principal stretch 0.7–1.4. Fixed vertices remain exact. A small inward optimization margin avoids accepting floating-point violations; the retained pose must satisfy the actual limits without tolerance relaxation. An infeasible or failed optimizer result cannot replace the feasible seed.

The real Huiye wave-left probe at 0.498046875 seconds converged in 66 iterations. Target RMS error fell from 399.673 to 374.802 pixels. The retained pose has zero inversions, no failing triangles, area ratio 0.500001–1.324015, maximum edge stretch 1.399891 and principal stretches 0.700001–1.399999.

This is a modest local improvement, not a solved natural-drape result. The fixed-boundary necessary target-error lower bound remains 86.595 pixels; that lower bound is not known to be attainable. Convergence of this local solver does not prove a global optimum. The fit reaches material/area limits and remains far from the requested target, so it must not be adopted as a whole-animation correction.

`character-cloth-feasible-target-v1.json` records the exact source and seed bundle, retained points and numeric evidence. No workbench registration or human decision changed. There was no new Runtime capture: temporal interpolation, seam contact and visual acceptance remain untested for this pose trial.

The next useful experiment must examine shape/path freedom rather than simply increasing the target penalty. Keep reviewed fixed vertices, ownership and material gates intact; any change in topology or boundary semantics needs separate evidence.
