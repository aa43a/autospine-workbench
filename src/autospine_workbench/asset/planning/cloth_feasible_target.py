"""Single-pose direction fitting with hard constraints and a feasible fallback."""
from .cloth_reachability import inspect
from .cloth_strain import prepare, stretches


def fit(setup, triangles, fixed_pose, free_vertices, target, seed, *, iterations=80):
    import numpy as np
    from scipy.optimize import minimize

    if type(iterations) is not int or not 1 <= iterations <= 500:
        raise ValueError('cloth_feasible_iterations')
    reach = inspect(setup, fixed_pose, triangles, free_vertices, target)
    rest = np.asarray(setup, dtype=float); fixed = np.asarray(fixed_pose, dtype=float)
    start = np.asarray(seed, dtype=float); desired = np.asarray(target, dtype=float)
    if start.shape != rest.shape or not np.isfinite(start).all():
        raise ValueError('cloth_feasible_seed')
    free = sorted(set(free_vertices)); pinned = sorted(set(range(len(rest)))-set(free))
    if not np.array_equal(start[pinned], fixed[pinned]):
        raise ValueError('cloth_feasible_fixed_seed')
    tri, inverse = prepare(setup, triangles)
    mask = np.asarray([any(i in free for i in t) for t in triangles])
    edges = np.asarray(sorted({tuple(sorted((a,b))) for t in triangles
                               for a,b in zip(t,t[1:]+t[:1])}))
    lengths = np.linalg.norm(rest[edges[:,0]]-rest[edges[:,1]], axis=1)
    scale = float(np.median(lengths))

    def unpack(x):
        p = fixed.copy(); p[free] = start[free]+scale*x.reshape(-1,2)
        return p

    def constraints(x):
        p = unpack(x)
        gradient = np.stack((p[tri[:,1]]-p[tri[:,0]], p[tri[:,2]]-p[tri[:,0]]),axis=2) @ inverse
        area = np.linalg.det(gradient)
        low, high = stretches(p, (tri,inverse))
        edge = np.linalg.norm(p[edges[:,0]]-p[edges[:,1]],axis=1)/lengths
        return np.concatenate((area-.5, 2.-area, 2.-edge, low[mask]-.7, 1.4-high[mask]))

    def objective(x):
        delta = (unpack(x)[free]-desired[free])/scale
        return float(np.mean(delta*delta))

    def jacobian(x):
        return ((unpack(x)[free]-desired[free])/scale).ravel()/len(free)

    zero = np.zeros(2*len(free))
    if np.min(constraints(zero)) < 0:
        raise ValueError('cloth_feasible_seed_outside_limits')
    best = zero.copy(); best_value = objective(best); feasible_iterations = 0

    def retain(x):
        nonlocal best, best_value, feasible_iterations
        if np.isfinite(x).all() and np.min(constraints(x)) >= 0:
            feasible_iterations += 1
            value = objective(x)
            if value < best_value:
                best = x.copy(); best_value = value

    result = minimize(objective, zero, jac=jacobian, method='SLSQP',
                      constraints=[{'type':'ineq','fun':lambda x: constraints(x)-1e-6}], callback=retain,
                      options={'maxiter':iterations,'ftol':1e-8})
    retain(result.x)
    points = unpack(best)
    before = float(np.sqrt(2*objective(zero))*scale)
    after = float(np.sqrt(2*best_value)*scale)
    low, high = stretches(points, (tri,inverse))
    return points.tolist(), dict(profile='hard-constrained-cloth-direction-v1', authority='none', selected=False,
        scope='single_pose_not_animation_or_visual_acceptance', optimizer_status=int(result.status),
        optimizer_success=bool(result.success), iterations=int(result.nit), feasible_iterations=feasible_iterations,
        improved=after < before-1e-8, before_target_rms_px=before, target_rms_px=after,
        target_rms_lower_bound_px=reach['target_rms_lower_bound_px'],
        min_constraint_margin=float(np.min(constraints(best))),
        material_min_stretch=float(np.min(low[mask])), material_max_stretch=float(np.max(high[mask])))
