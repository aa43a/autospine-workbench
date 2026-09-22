"""Uniform-edge local/global ARAP experiment with hard pins and movement cap."""
import math
import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import factorized


def solve(setup, posed, triangles, free, budget, iterations=64):
    p, origin = np.asarray(setup, dtype=float), np.asarray(posed, dtype=float)
    if (p.shape != origin.shape or p.ndim != 2 or p.shape[1] != 2 or
            not np.isfinite(p).all() or not np.isfinite(origin).all() or
            not math.isfinite(budget) or budget <= 0 or not 1 <= iterations <= 256):
        raise ValueError('local_arap_input_invalid')
    free = sorted(set(free))
    if any(type(i) is not int or not 0 <= i < len(p) for i in free):
        raise ValueError('local_arap_free_invalid')
    edges = sorted({tuple(sorted((a, b))) for t in triangles for a, b in zip(t, t[1:]+t[:1])})
    if any(a == b or a < 0 or b >= len(p) for a, b in edges):
        raise ValueError('local_arap_topology_invalid')
    neighbors = [set() for _ in p]
    for a, b in edges: neighbors[a].add(b); neighbors[b].add(a)
    # Each free component must connect to a pinned vertex.
    reached = set(range(len(p)))-set(free)
    pending = list(reached)
    while pending:
        for other in neighbors[pending.pop()]-reached:
            reached.add(other); pending.append(other)
    if set(free)-reached: raise ValueError('local_arap_unpinned_component')
    if not free: return origin.tolist(), dict(iterations=0, maximum_displacement=0.)
    lookup = {v: i for i, v in enumerate(free)}
    rows, cols, values = [], [], []
    for vertex in free:
        i = lookup[vertex]
        rows.append(i); cols.append(i); values.append(len(neighbors[vertex]))
        for other in neighbors[vertex]:
            if other in lookup: rows.append(i); cols.append(lookup[other]); values.append(-1)
    matrix = coo_matrix((values, (rows, cols)), shape=(len(free), len(free))).tocsc()
    linear_solve = factorized(matrix)
    q = origin.copy()
    for _ in range(iterations):
        rotations = []
        for i, adjacent in enumerate(neighbors):
            covariance = sum((np.outer(q[i]-q[j], p[i]-p[j]) for j in adjacent), np.zeros((2, 2)))
            u, _, vt = np.linalg.svd(covariance)
            correction = np.diag([1., np.linalg.det(u@vt)])
            rotations.append(u@correction@vt)
        rhs = np.zeros((len(free), 2))
        for vertex in free:
            for other in neighbors[vertex]:
                rhs[lookup[vertex]] += .5*(rotations[vertex]+rotations[other])@(p[vertex]-p[other])
                if other not in lookup: rhs[lookup[vertex]] += origin[other]
        candidate = np.column_stack([linear_solve(rhs[:, axis]) for axis in (0, 1)])
        delta = candidate-origin[free]
        distances = np.linalg.norm(delta, axis=1)
        q[free] = origin[free]+delta*np.minimum(1., budget/np.maximum(distances, 1e-12))[:, None]
    return q.tolist(), dict(profile='uniform-edge-local-arap-v1-experiment', iterations=iterations,
        maximum_displacement=float(np.linalg.norm(q-origin, axis=1).max()),
        authority='none', scope='shape_candidate_no_inversion_or_temporal_guarantee')
