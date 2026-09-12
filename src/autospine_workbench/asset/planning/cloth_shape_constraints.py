"""Sparse area/edge refinement of a validated pinned cloth shape trial."""
from .cloth_shape_solver import solve
from .component_local_solver import metrics


def refine(setup, triangles, fixed_pose, free_vertices, target, *, seed=None, temporal=False, interval_maps=(), continuation=False):
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
    previous = np.asarray(seed, dtype=float) if temporal and seed is not None else None
    area_blocks = 2+2*len(interval_maps) if interval_maps else (4 if previous is not None else 2)
    sparsity = lil_matrix((area_blocks*nt+ne+2*n, 2*n), dtype=int)
    for i, t in enumerate(tri):
        for v in t:
            if v in lookup:
                j = 2*lookup[v]
                for block in range(area_blocks): sparsity[block*nt+i, j:j+2] = 1
    for i, edge in enumerate(edges):
        for v in edge:
            if v in lookup: sparsity[area_blocks*nt+i, 2*lookup[v]:2*lookup[v]+2] = 1
    for i in range(2*n): sparsity[area_blocks*nt+ne+i, i] = 1
    def unpack(x):
        p = fixed.copy(); p[free] = start[free]+scale*x.reshape(n, 2)
        return p
    def residual(x):
        p = unpack(x); ratio = areas(p)/area
        stretch = np.linalg.norm(p[edges[:, 0]]-p[edges[:, 1]], axis=1)/lengths
        residuals = [np.maximum(.55-ratio, 0), np.maximum(ratio-1.9, 0)]
        if interval_maps:
            for bias, transform in interval_maps:
                subframe = bias+np.einsum('nij,nj->ni', transform, p)
                ratio = areas(subframe)/area
                residuals.extend((np.maximum(.55-ratio, 0), np.maximum(ratio-1.9, 0)))
        elif previous is not None:
            from .cloth_interval_area import bounds
            low, high = bounds(areas(previous)/area, areas((previous+p)/2)/area, ratio)
            residuals.extend((np.maximum(.55-low, 0), np.maximum(high-1.9, 0)))
        return np.concatenate((*residuals, np.maximum(stretch-1.9, 0), .001*x))
    x0 = (np.asarray(seed)[free]-start[free]).ravel()/scale if continuation and seed is not None else np.zeros(2*n)
    fit = least_squares(residual, x0, jac_sparsity=sparsity.tocsr(),
                        max_nfev=150, ftol=1e-9, xtol=1e-9, gtol=1e-9)
    result = unpack(fit.x)
    if not np.isfinite(result).all(): raise ValueError('cloth_shape_constraints_nonfinite')
    evidence.update(profile='pinned-arap-area-edge-refinement-v1', evaluations=int(fit.nfev),
                    optimizer_status=int(fit.status), before_refinement=metrics(setup, initial, triangles),
                    maximum_displacement_px=float(np.max(np.linalg.norm(result-fixed, axis=1))),
                    constraint_targets=dict(min_area_ratio=.55, max_area_ratio=1.9, max_edge_stretch=1.9))
    if temporal:
        evidence.update(profile='pinned-arap-area-edge-world-interval-v2',
                        temporal_scope='linear_world_path_requires_exact_spine_resampling')
    if interval_maps:
        evidence.update(profile='pinned-arap-area-edge-spine-subframes-v3',
                        temporal_scope='exact_spine_quarter_samples_not_continuous_proof')
    if continuation:
        evidence.update(profile='pinned-arap-spine-subframes-continuation-v4',
                        continuation_seed='previous_world_pose' if seed is not None else 'setup')
    return result.tolist(), evidence
