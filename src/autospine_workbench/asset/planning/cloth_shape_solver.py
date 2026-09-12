"""Pinned local/global cloth shape trial. No admission, ownership, or physics claim."""
import math


def solve(setup, triangles, fixed_pose, free_vertices, target, *, iterations=80, seed=None):
    import numpy as np
    import scipy
    from scipy.sparse import coo_matrix, eye
    from scipy.sparse.linalg import factorized
    if type(iterations) is not int or not 1 <= iterations <= 300:
        raise ValueError('cloth_shape_iterations')
    n = len(setup); free = sorted(set(free_vertices))
    if (not n or len(fixed_pose) != n or len(target) != n or not free
            or any(type(i) is not int or i < 0 or i >= n for i in free)
            or any(len(p) != 2 or not all(math.isfinite(x) for x in p)
                   for points in (setup, fixed_pose, target) for p in points)
            or not triangles or any(len(t) != 3 or len(set(t)) != 3
                or any(type(i) is not int or i < 0 or i >= n for i in t) for t in triangles)):
        raise ValueError('cloth_shape_input')
    rest = np.asarray(setup, dtype=float); pinned = np.asarray(fixed_pose, dtype=float)
    for a, b, c in triangles:
        u, v = rest[b]-rest[a], rest[c]-rest[a]
        if abs(u[0]*v[1]-u[1]*v[0]) < 1e-8:
            raise ValueError('cloth_shape_degenerate')
    desired = np.asarray(target, dtype=float); points = pinned.copy()
    if seed is not None and (len(seed) != n or any(len(p) != 2 or
            not all(math.isfinite(x) for x in p) for p in seed)):
        raise ValueError('cloth_shape_seed')
    points[free] = np.asarray(seed, dtype=float)[free] if seed is not None else desired[free]
    edges = sorted({tuple(sorted((a, b))) for t in triangles for a, b in zip(t, t[1:]+t[:1])})
    neighbors = [set() for _ in range(n)]
    for a, b in edges:
        if np.linalg.norm(rest[a]-rest[b]) < 1e-8:
            raise ValueError('cloth_shape_degenerate')
        neighbors[a].add(b); neighbors[b].add(a)
    # Every movable connected component must meet a fixed boundary.
    unseen = set(free); movable = set(free)
    while unseen:
        stack = [min(unseen)]; anchored = False
        while stack:
            i = stack.pop()
            if i not in unseen: continue
            unseen.remove(i)
            anchored |= bool(neighbors[i]-movable)
            stack.extend(sorted(neighbors[i] & unseen))
        if not anchored: raise ValueError('cloth_shape_unanchored')
    lookup = {v: i for i, v in enumerate(free)}; rows = []; cols = []; values = []
    for i in free:
        rows.append(lookup[i]); cols.append(lookup[i]); values.append(len(neighbors[i]))
        for j in sorted(neighbors[i] & movable):
            rows.append(lookup[i]); cols.append(lookup[j]); values.append(-1.)
    # Weak positional prior selects the requested direction; it is not a geometric pass criterion.
    prior = .01
    system = coo_matrix((values, (rows, cols)), shape=(len(free), len(free))).tocsc()
    factor = factorized(system + prior*eye(len(free), format='csc'))
    rotations = np.repeat(np.eye(2)[None, :, :], n, axis=0)
    delta = 0.
    for _ in range(iterations):
        for i in range(n):
            js = sorted(neighbors[i])
            covariance = (points[i]-points[js]).T @ (rest[i]-rest[js])
            u, _, vt = np.linalg.svd(covariance)
            if np.linalg.det(u @ vt) < 0: u[:, -1] *= -1
            rotations[i] = u @ vt
        rhs = prior*desired[free].copy()
        for i in free:
            for j in sorted(neighbors[i]):
                rhs[lookup[i]] += .5*(rotations[i]+rotations[j]) @ (rest[i]-rest[j])
                if j not in movable: rhs[lookup[i]] += pinned[j]
        updated = np.column_stack([factor(rhs[:, k]) for k in range(2)])
        delta = float(np.max(np.linalg.norm(updated-points[free], axis=1)))
        points[free] = updated
    if not np.isfinite(points).all(): raise ValueError('cloth_shape_nonfinite')
    return points.tolist(), dict(profile='pinned-uniform-arap-direction-prior-v1', authority='none',
        numpy_version=np.__version__, scipy_version=scipy.__version__,
        iterations=iterations, seeded=seed is not None, final_iteration_delta_px=delta, free_vertices=free,
        maximum_displacement_px=float(np.max(np.linalg.norm(points-pinned, axis=1))),
        status='trial_requires_geometry_contact_and_runtime', selected=False)
