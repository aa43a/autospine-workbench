"""Sparse area/edge refinement of a validated pinned cloth shape trial."""
from .cloth_shape_solver import solve
from .component_local_solver import metrics


def refine(setup, triangles, fixed_pose, free_vertices, target, *, seed=None):
    import numpy as np
    from scipy.optimize import least_squares
    from scipy.sparse import lil_matrix
    initial, evidence = solve(setup, triangles, fixed_pose, free_vertices, target, seed=seed)
    free = evidence['free_vertices']; rest = np.asarray(setup, dtype=float)
    fixed = np.asarray(fixed_pose, dtype=float); start = np.asarray(initial)
    tri = np.asarray(triangles, dtype=int)
    edges = np.asarray(sorted({tuple(sorted((a, b))) for t in triangles for a, b in zip(t, t[1:]+t[:1])}))
    def areas(p):
        a = p[tri[:, 1]]-p[tri[:, 0]]; b = p[tri[:, 2]]-p[tri[:, 0]]
        return .5*(a[:, 0]*b[:, 1]-a[:, 1]*b[:, 0])
    area = areas(rest); lengths = np.linalg.norm(rest[edges[:, 0]]-rest[edges[:, 1]], axis=1)
    scale = float(np.median(lengths)); nt = len(tri); ne = len(edges); n = len(free)
    lookup = {v: i for i, v in enumerate(free)}
    sparsity = lil_matrix((2*nt+ne+2*n, 2*n), dtype=int)
    for i, t in enumerate(tri):
        for v in t:
            if v in lookup:
                j = 2*lookup[v]; sparsity[i, j:j+2] = 1; sparsity[nt+i, j:j+2] = 1
    for i, edge in enumerate(edges):
        for v in edge:
            if v in lookup: sparsity[2*nt+i, 2*lookup[v]:2*lookup[v]+2] = 1
    for i in range(2*n): sparsity[2*nt+ne+i, i] = 1
    def unpack(x):
        p = fixed.copy(); p[free] = start[free]+scale*x.reshape(n, 2)
        return p
    def residual(x):
        p = unpack(x); ratio = areas(p)/area
        stretch = np.linalg.norm(p[edges[:, 0]]-p[edges[:, 1]], axis=1)/lengths
        return np.concatenate((np.maximum(.55-ratio, 0), np.maximum(ratio-1.9, 0),
                               np.maximum(stretch-1.9, 0), .001*x))
    fit = least_squares(residual, np.zeros(2*n), jac_sparsity=sparsity.tocsr(),
                        max_nfev=150, ftol=1e-9, xtol=1e-9, gtol=1e-9)
    result = unpack(fit.x)
    if not np.isfinite(result).all(): raise ValueError('cloth_shape_constraints_nonfinite')
    evidence.update(profile='pinned-arap-area-edge-refinement-v1', evaluations=int(fit.nfev),
                    optimizer_status=int(fit.status), before_refinement=metrics(setup, initial, triangles),
                    maximum_displacement_px=float(np.max(np.linalg.norm(result-fixed, axis=1))),
                    constraint_targets=dict(min_area_ratio=.55, max_area_ratio=1.9, max_edge_stretch=1.9))
    return result.tolist(), evidence
