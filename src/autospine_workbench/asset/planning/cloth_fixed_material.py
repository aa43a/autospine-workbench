"""Necessary material bounds on edges whose endpoints a cloth solver cannot move."""
import math


def inspect(setup, points, triangles, free_vertices, lower=.7, upper=1.4):
    free = set(free_vertices)
    if not 0 < lower <= upper or len(setup) != len(points): raise ValueError('cloth_fixed_material_input')
    edges = sorted({tuple(sorted((a, b))) for t in triangles if any(v in free for v in t)
                    for a, b in zip(t, t[1:]+t[:1]) if a not in free and b not in free})
    rows = []
    for a, b in edges:
        length = math.dist(setup[a], setup[b]); current = math.dist(points[a], points[b])
        if not math.isfinite(length+current) or length < 1e-10: raise ValueError('cloth_fixed_material_degenerate')
        ratio = current/length
        if ratio < lower or ratio > upper: rows.append(dict(edge=[a, b], stretch=ratio))
    return dict(status='infeasible_with_fixed_endpoints' if rows else 'no_fixed_edge_counterexample',
                checked_edges=len(edges), violations=rows,
                limitation='necessary_edge_bound_not_a_global_feasibility_proof')
