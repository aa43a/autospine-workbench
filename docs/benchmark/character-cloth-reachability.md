# Fixed-boundary cloth target reachability

The `inspect-character-cloth-reach.py` diagnostic checks a necessary condition before further direction-target optimization. It does not modify bindings, labels, weights, animations, or acceptance decisions.

For every free vertex, a setup mesh-edge path to a fixed anchor bounds its possible distance from that anchor. A principal stretch upper bound of 1.4 implies every edge on that path can grow by at most 1.4. A target outside the resulting disk has an unavoidable positional error. The report retains the strongest anchor/path witness for each vertex and combines these independent lower bounds into an RMS lower bound.

The graph includes only triangles touching free vertices, matching the material-check scope. Current animated anchor positions are used; setup anchor positions cannot substitute for them. Unanchored components remain explicit. No counterexample does not prove feasibility: lower stretch, area, inversion, contact and visual constraints still apply.

## Recorded result

See `character-cloth-reachability-v1.json` for the exact source bundle and profile. Huiye's left sleeve, `wave-left` at 0.498046875 seconds, has 123 free vertices and 16 fixed anchors. Of those free vertices, 112 have targets outside at least one necessary reach disk. The target RMS error lower bound is approximately **86.6 px**.

This rejects exact satisfaction of the current world-hold direction target under the existing boundary and upper-stretch constraint. It does not reject every natural drape shape, nor justify changing reviewed ownership or relaxing material limits. The next solver experiment should generate a boundary-compatible target and then independently check geometry, material, subframes and official Runtime playback. No new animation was adopted or Runtime capture claimed by this diagnostic.

## Validation

Five numerical tests cover analytic bounds, moving anchors, similarity transforms, deterministic witnesses, disconnected vertices and invalid/overflow inputs. Three repository source-budget checks also pass. Production code and the command remain separate small modules.
