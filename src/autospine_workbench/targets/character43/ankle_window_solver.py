"""Experimental jointly constrained ankle window; never automatically adopted."""
import math
from .affine_leg_ik import _local
from .affine_pose import matrices


def solve_window(document, animation, times, targets, reference):
    import numpy as np
    from scipy.optimize import minimize
    t = np.asarray(times, dtype=float)
    goal = np.asarray(targets, dtype=float)
    if (not 2 <= len(t) <= 32 or t[0] != 0 or not np.isfinite(t).all()
            or np.any(np.diff(t) <= 0) or goal.shape != (len(t), 2, 2)
            or not np.isfinite(goal).all() or not math.isfinite(reference) or reference <= 0):
        raise ValueError('ankle_window_input_invalid')
    bones = {b['name']: b for b in document['bones']}
    tracks = document['animations'][animation]['bones']
    if bones['root'].get('parent') or any('curve' in k for r in tracks.values() for keys in r.values() for k in keys):
        raise ValueError('ankle_window_requires_linear_root')
    # Preserve every original knot when reconstructing base + correction.
    if any(0 < k.get('time', 0) < t[-1] and k['time'] not in times
           for row in tracks.values() for keys in row.values() for k in keys):
        raise ValueError('ankle_window_missing_source_knot')
    sampled = np.asarray(sorted(set(times) | {float(a+(b-a)*i/4)
                         for a, b in zip(t, t[1:]) for i in (1, 2, 3)}))
    goal = np.stack([np.interp(sampled, t, goal[:, i, j])
                     for i in (0, 1) for j in (0, 1)], axis=1).reshape((-1, 2, 2))
    geometry = []
    for time in sampled:
        pose = matrices(document, animation, float(time))
        row = []
        for side in ('l', 'r'):
            upper, lower, tip = ['%s_%s' % (p, side) for p in ('thigh', 'calf', 'foot')]
            if bones[lower].get('parent') != upper or bones[tip].get('parent') != lower:
                raise ValueError('ankle_window_direct_chain_required')
            ancestor = upper
            while ancestor and ancestor != 'root':
                ancestor = bones[ancestor].get('parent')
            if ancestor != 'root':
                raise ValueError('ankle_window_root_ancestry')
            parent = pose[bones[upper]['parent']]
            ua, _, _, sx, sy = _local(bones[upper], tracks.get(upper, {}), time)
            la, lx, ly, lsx, lsy = _local(bones[lower], tracks.get(lower, {}), time)
            _, tx, ty, _, _ = _local(bones[tip], tracks.get(tip, {}), time)
            row.append([*parent[:4], *pose[upper][4:6], math.radians(ua), sx, sy,
                        math.radians(la), lx, ly, tx*lsx, ty*lsy])
        geometry.append(row)
    g = np.asarray(geometry)

    def endpoints(x):
        v = x.reshape((-1, 6))
        v = np.stack([np.interp(sampled, t, v[:, i]) for i in range(6)], axis=1)
        ua = g[:, :, 6] + v[:, [2, 4]]
        la = g[:, :, 9] + v[:, [3, 5]]
        rx = np.cos(la)*g[:, :, 12] - np.sin(la)*g[:, :, 13]
        ry = np.sin(la)*g[:, :, 12] + np.cos(la)*g[:, :, 13]
        lx, ly = g[:, :, 7]*(g[:, :, 10]+rx), g[:, :, 8]*(g[:, :, 11]+ry)
        vx, vy = np.cos(ua)*lx-np.sin(ua)*ly, np.sin(ua)*lx+np.cos(ua)*ly
        return np.stack((g[:, :, 4]+g[:, :, 0]*vx+g[:, :, 1]*vy+reference*v[:, 0, None],
                         g[:, :, 5]+g[:, :, 2]*vx+g[:, :, 3]*vy+reference*v[:, 1, None]), axis=2)

    dt = np.diff(t)
    def checks(x, headroom=1.):
        v = x.reshape((-1, 6))
        delta = np.diff(v, axis=0)
        return dict(root_displacement=(.15*headroom)**2-np.sum(v[:, :2]**2, axis=1),
                    root_speed=(2*dt*headroom)**2-np.sum(delta[:, :2]**2, axis=1),
                    rotation_speed=np.pi*dt[:, None]*headroom-np.abs(delta[:, 2:]),
                    endpoint_residual=(.01*headroom)**2-np.sum(((endpoints(x)-goal)/reference)**2, axis=2),
                    rotation_magnitude=math.pi/6-np.abs(v[:, 2:]))

    def objective(x):
        v = x.reshape((-1, 6))
        return float(np.sum(((endpoints(x)-goal)/reference)**2) + 1e-8*np.sum(v*v)
                     + 1e-8*np.sum(np.diff(v, axis=0)**2))

    bounds = [(-.15, .15)]*2+[(-math.pi/6, math.pi/6)]*4
    bounds = [(0., 0.)]*6 + bounds*(len(t)-1)
    trials = []
    # Opposite knee seeds allow a temporal path to leave the greedy IK branch.
    for sign in (0, -1, 1):
        seed = np.zeros((len(t), 6))
        seed[:, [3, 5]] = sign*np.minimum(t[:, None]*math.pi*.5, .2)
        result = minimize(objective, seed.ravel(), method='SLSQP', bounds=bounds,
                          constraints=[dict(type='ineq', fun=lambda x: np.concatenate(
                              [r.ravel() for r in checks(x, .99999).values()]))],
                          options=dict(maxiter=300, ftol=1e-12))
        margins = checks(result.x)
        failed = [k for k, v in margins.items() if not np.isfinite(v).all() or np.any(v < 0)]
        errors = np.linalg.norm(endpoints(result.x)-goal, axis=2)
        trials.append(dict(seed=sign, solver_success=bool(result.success), iterations=int(result.nit),
                           failed_checks=failed, maximum_error_px=float(errors.max()),
                           values=result.x.reshape((-1, 6)).tolist()))
    valid = [r for r in trials if not r['failed_checks']]
    best = min(valid, key=lambda r: r['maximum_error_px']) if valid else None
    return dict(profile='moving-ankle-window-interpolated-experiment-v2', selected=False, authority='none',
                status='candidate' if best else 'no_bounded_path_found', times=times,
                constraint_times=sampled.tolist(),
                solution=best['values'] if best else None, trials=trials,
                parameter_units='root_over_reference_then_four_rotation_deltas_in_radians',
                scope='sampled_window_only_requires_full_timeline_geometry_runtime_checks')
