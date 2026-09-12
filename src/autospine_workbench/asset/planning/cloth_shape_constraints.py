"""Sparse area/edge refinement of a validated pinned cloth shape trial."""
from .cloth_shape_solver import solve
from .component_local_solver import metrics


def refine(setup, triangles, fixed_pose, free_vertices, target, *, seed=None, temporal=False, interval_maps=(), continuation=False, material=False, material_subframes=False, target_prior=0.):
    import numpy as np
    from scipy.optimize import least_squares
    from scipy.sparse import lil_matrix
    if material_subframes and not material: raise ValueError('cloth_material_subframes_requires_material')
    import math
    if type(target_prior) not in (int, float) or not math.isfinite(target_prior) or not 0 <= target_prior <= 1:
        raise ValueError('cloth_target_prior_invalid')
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
    if material:
        from .cloth_strain import prepare, stretches
        strain_context = prepare(setup, triangles)
        material_mask = np.asarray([any(v in lookup for v in t) for t in tri], dtype=float)
        area_blocks += 2+2*len(interval_maps) if material_subframes else 2
    sparsity = lil_matrix((area_blocks*nt+ne+(4 if target_prior else 2)*n, 2*n), dtype=int)
    for i, t in enumerate(tri):
        for v in t:
            if v in lookup:
                j = 2*lookup[v]
                for block in range(area_blocks): sparsity[block*nt+i, j:j+2] = 1
    for i, edge in enumerate(edges):
        for v in edge:
            if v in lookup: sparsity[area_blocks*nt+i, 2*lookup[v]:2*lookup[v]+2] = 1
    for i in range(2*n): sparsity[area_blocks*nt+ne+i, i] = 1
    if target_prior:
        for i in range(2*n): sparsity[area_blocks*nt+ne+2*n+i, i] = 1
    desired = np.asarray(target, dtype=float)
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
        if material:
            low, high = stretches(p, strain_context)
            residuals.extend((material_mask*np.maximum(.72-low, 0), material_mask*np.maximum(high-1.38, 0)))
            if material_subframes:
                for bias, transform in interval_maps:
                    low, high = stretches(bias+np.einsum('nij,nj->ni', transform, p), strain_context)
                    residuals.extend((material_mask*np.maximum(.72-low, 0), material_mask*np.maximum(high-1.38, 0)))
        residuals.extend((np.maximum(stretch-1.9, 0), .001*x))
        if target_prior: residuals.append(target_prior*((p[free]-desired[free])/scale).ravel())
        return np.concatenate(residuals)
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
    if material:
        low, high = stretches(result, strain_context); selected = material_mask > 0
        evidence.update(profile='pinned-cloth-principal-stretch-trial-v5',
                        material_min_stretch=float(np.min(low[selected])),
                        material_max_stretch=float(np.max(high[selected])),
                        material_trial_limits=dict(min_stretch=.7, max_stretch=1.4),
                        material_passed=bool(np.all(low[selected] >= .7) and np.all(high[selected] <= 1.4)))
    if material_subframes:
        evidence.update(profile='pinned-cloth-principal-stretch-subframes-v6',
                        material_temporal_scope='exact_quarter_samples_requires_dense_check')
    if target_prior:
        evidence.update(profile='pinned-cloth-explicit-direction-target-v7', target_prior=target_prior,
                        target_rms_error_px=float(np.sqrt(np.mean(np.sum((result[free]-desired[free])**2, axis=1)))),
                        target_scope='position_prior_not_gravity_or_contact')
    return result.tolist(), evidence
