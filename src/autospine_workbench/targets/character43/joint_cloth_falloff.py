"""Smooth material distance from the existing fixed clothing vertices.

Use mesh edges, rather than distance to each helper pivot, so the first free
row cannot jump directly to full response beside a nearly fixed body row.
Components without a fixed material point remain stationary.
"""
import heapq
import math

PROFILE = 'material-falloff-v2'
LEGACY = 'helper-local-v1'


def falloff(points, triangles, pinned):
    count = len(points); fixed = set(pinned)
    graph = [dict() for _ in points]
    for triangle in triangles:
        for a, b in zip(triangle, triangle[1:] + triangle[:1]):
            length = math.dist(points[a], points[b])
            graph[a][b] = graph[b][a] = length
    distances = [math.inf] * count; queue = []
    for index in fixed:
        distances[index] = 0.; heapq.heappush(queue, (0., index))
    while queue:
        distance, index = heapq.heappop(queue)
        if distance != distances[index]: continue
        for neighbor, length in graph[index].items():
            candidate = distance + length
            if candidate < distances[neighbor]:
                distances[neighbor] = candidate
                heapq.heappush(queue, (candidate, neighbor))
    # Share the release distance across this material. A tiny rooted island must
    # not reach full response after one narrow edge beside its fixed vertices.
    width = max((d for d in distances if math.isfinite(d)), default=0.)
    values = [0.] * count; widths = []; unanchored = []; unseen = set(range(count))
    while unseen:
        seed = min(unseen); unseen.remove(seed); component = [seed]; stack = [seed]
        while stack:
            for neighbor in graph[stack.pop()]:
                if neighbor in unseen:
                    unseen.remove(neighbor); component.append(neighbor); stack.append(neighbor)
        if not any(index in fixed for index in component):
            unanchored.extend(component); continue
        widths.append(max(distances[index] for index in component))
        if width <= 1e-9: continue
        for index in component:
            t = min(1., distances[index] / width)
            values[index] = t * t * (3. - 2. * t)
    return values, dict(profile=PROFILE, distance_basis='setup_mesh_edge_geodesic',
        interpolation='smoothstep_zero_slope_at_fixed_and_free_end',
        fixed_vertices_preserved=True, transition_width_px=width, rooted_component_depths_px=widths,
        unanchored_vertices=sorted(unanchored), vertex_count=count)
