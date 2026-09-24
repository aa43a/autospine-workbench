"""Necessary fixed-boundary conditions before attempting interior refinement.

For a centroid fan, the three signed child areas sum to the parent's area
for *any* center position. Their setup areas are one third of the parent's.
Thus their mean area ratio equals the parent ratio. If that ratio is outside
the allowed interval, no center-only edit can make all children admissible.
Original edges are also unchanged. Passing these checks is not a proof of
feasibility for edge lengths, texture, neighboring regions or intermediate time.
"""
import math


def _area(points, triangle):
    a, b, c = [points[i] for i in triangle]
    return ((b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]))/2


def inspect(setup, posed, triangles, selected, minimum=.5, maximum=2., edge_limit=2.):
    if (not all(type(v) in (int, float) and math.isfinite(v)
                for v in (minimum, maximum, edge_limit)) or
            not 0 < minimum <= maximum or edge_limit < 1):
        raise ValueError('pose_refinement_limits_invalid')
    if (len(setup) != len(posed) or not setup or any(
            len(p) != 2 or any(type(v) not in (int, float) or not math.isfinite(v) for v in p)
            for points in (setup, posed) for p in points)):
        raise ValueError('pose_refinement_points_invalid')
    if any(len(t) != 3 or len(set(t)) != 3 or any(
            type(v) is not int or not 0 <= v < len(setup) for v in t) for t in triangles):
        raise ValueError('pose_refinement_triangles_invalid')
    if (not selected or any(type(i) is not int or not 0 <= i < len(triangles) for i in selected)
            or len(set(selected)) != len(selected)):
        raise ValueError('pose_refinement_selection_invalid')
    records = []
    for index in selected:
        triangle = triangles[index]
        initial = _area(setup, triangle)
        if abs(initial) < 1e-12:
            raise ValueError('pose_refinement_setup_degenerate')
        ratio = _area(posed, triangle)/initial
        reasons, edges = [], []
        if ratio < minimum or ratio > maximum:
            reasons.append('fixed_parent_signed_area_outside_limits')
        for a, b in zip(triangle, triangle[1:]+triangle[:1]):
            rest = math.dist(setup[a], setup[b])
            if rest <= 1e-12:
                raise ValueError('pose_refinement_setup_degenerate')
            stretch = math.dist(posed[a], posed[b])/rest
            if stretch > edge_limit:
                edges.append(dict(vertices=[a, b], stretch=stretch))
        if edges:
            reasons.append('fixed_boundary_edge_exceeds_limit')
        if reasons:
            records.append(dict(triangle=index, vertices=list(triangle), area_ratio=ratio,
                                reasons=reasons, edges=edges))
    return dict(profile='fixed-triangle-interior-feasibility-v1',
        status='infeasible_with_fixed_triangle_boundaries' if records else 'no_counterexample',
        selected_triangle_count=len(selected), counterexamples=records,
        limits=dict(minimum_area_ratio=minimum, maximum_area_ratio=maximum, max_edge_stretch=edge_limit),
        scope='centroid_controls_only_original_vertices_fixed',
        feasible_proven=False, authority='none', selected=False)
