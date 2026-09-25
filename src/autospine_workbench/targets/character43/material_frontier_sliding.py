"""Compare material locking with bounded sliding on the same observed arc."""
from collections import defaultdict
import numpy as np


def topology(samples):
    """Connect only two-crossing grid cells; keep ambiguous cells disconnected."""
    cells = defaultdict(list)
    blocked = {tuple(cell) for item in samples for cell in item.get('ambiguous_cells', [])}
    for i, item in enumerate(samples):
        (y, x), (v, u) = item['edge']
        if y == v and abs(x-u) == 1:
            for key in ((y-1, min(x, u)), (y, min(x, u))):
                cells[key].append(i)
        elif x == u and abs(y-v) == 1:
            for key in ((min(y, v), x-1), (min(y, v), x)):
                cells[key].append(i)
        else:
            raise ValueError('frontier_sliding_edge_invalid')
    edges = sorted({tuple(sorted(ids)) for cell, ids in cells.items() if len(ids) == 2 and cell not in blocked})
    adjacency = [set() for _ in samples]
    for a, b in edges:
        adjacency[a].add(b); adjacency[b].add(a)
    components, labels = [], [-1]*len(samples)
    for i in range(len(samples)):
        if labels[i] != -1:
            continue
        pending, group = [i], []
        labels[i] = len(components)
        while pending:
            v = pending.pop(); group.append(v)
            for w in sorted(adjacency[v]):
                if labels[w] == -1:
                    labels[w] = labels[i]; pending.append(w)
        components.append(sorted(group))
    return dict(edges=[list(e) for e in edges], components=components,
                labels=labels, ambiguous_cells=len(blocked | {cell for cell, ids in cells.items() if len(ids)>2}))


def compare(samples, arm_points, body_points):
    """Never jump to another arc or extrapolate past observed segment endpoints.

    Distance is unsigned: it neither proves a visible crack nor classifies which
    side is occluded. No deformation or automatic acceptance is performed.
    """
    arm, body = np.asarray(arm_points, float), np.asarray(body_points, float)
    if (arm.shape != (len(samples), 2) or body.shape != arm.shape
            or not np.isfinite(arm).all() or not np.isfinite(body).all()):
        raise ValueError('frontier_sliding_points_invalid')
    graph = topology(samples)
    rows = []
    for i, point in enumerate(arm):
        edges = [(a, b) for a, b in graph['edges'] if graph['labels'][a] == graph['labels'][i]]
        fixed = float(np.linalg.norm(point-body[i]))
        best, target, segment, factor = fixed, body[i].tolist(), None, None
        usable = 0
        for a, b in edges:
            direction = body[b]-body[a]
            square = float(direction@direction)
            if square <= 1e-16:
                continue
            usable += 1
            u = float(np.clip((point-body[a])@direction/square, 0, 1))
            q = body[a]+u*direction
            distance = float(np.linalg.norm(point-q))
            if distance < best:
                best, target, segment, factor = distance, q.tolist(), [a, b], u
        rows.append(dict(sample=i, component=graph['labels'][i], fixed_distance_px=fixed,
                         sliding_distance_px=best if usable else None,
                         target=target if usable else None, segment=segment, segment_fraction=factor,
                         status='bounded_arc_comparison' if usable else 'insufficient_arc_support'))
    return dict(topology=graph, records=rows, selected=False, authority='none',
                scope='same_arc_distance_not_signed_gap_or_repair')
