"""Joint root/leg endpoint search; a solution still needs animation and mesh QA."""
import math

from .affine_leg_ik import _local, _rotate
from .affine_pose import matrices


def solve(document, animation, time, contacts, reference_length, *, maximum_degrees=30, previous=None,
          maximum_rotation_speed=None, preserve_pose=False, maximum_error_px=None):
    import numpy as np
    from scipy.optimize import minimize
    if type(preserve_pose) is not bool:
        raise ValueError('joint_support_pose_mode_invalid')
    if (not math.isfinite(reference_length) or reference_length <= 0
            or not math.isfinite(maximum_degrees) or not 0 < maximum_degrees <= 90
            or not 1 <= len(contacts) <= 2):
        raise ValueError('joint_support_limits_invalid')
    residual_limit = .01*reference_length if maximum_error_px is None else maximum_error_px
    if not math.isfinite(residual_limit) or not 0 < residual_limit <= .01*reference_length:
        raise ValueError('joint_support_residual_limit_invalid')
    if maximum_rotation_speed is not None and (not math.isfinite(maximum_rotation_speed) or maximum_rotation_speed <= 0):
        raise ValueError('joint_support_rotation_speed_invalid')
    bones = {b['name']: b for b in document['bones']}
    if bones['root'].get('parent'):
        raise ValueError('joint_support_root_parent')
    tracks = document['animations'][animation].get('bones', {})
    if any('curve' in k for row in tracks.values() for keys in row.values() for k in keys):
        raise ValueError('joint_support_linear_required')
    pose = matrices(document, animation, time)
    chains = []; used = set()
    previous_root = None; step_limit = None
    if previous is not None:
        elapsed = time-previous['time']
        previous_root = np.asarray(previous['root_shift'], dtype=float)/reference_length
        if elapsed <= 0 or not math.isfinite(elapsed) or previous_root.shape != (2,) or not np.isfinite(previous_root).all():
            raise ValueError('joint_support_previous_invalid')
        step_limit = 2*elapsed
    for row in contacts:
        upper, lower, tip = (row[k] for k in ('upper', 'lower', 'tip'))
        if bones[lower].get('parent') != upper or bones[tip].get('parent') != lower:
            raise ValueError('joint_support_direct_chain_required')
        if used.intersection((upper, lower, tip)):
            raise ValueError('joint_support_disjoint_chains_required')
        used.update((upper, lower, tip))
        ancestor = upper
        while ancestor and ancestor != 'root': ancestor = bones[ancestor].get('parent')
        if ancestor != 'root': raise ValueError('joint_support_root_ancestry')
        target = row['target']
        if len(target) != 2 or not all(math.isfinite(v) for v in target):
            raise ValueError('joint_support_target_invalid')
        parent = pose[bones[upper]['parent']]
        ua, _, _, usx, usy = _local(bones[upper], tracks.get(upper, {}), time)
        la, lx, ly, lsx, lsy = _local(bones[lower], tracks.get(lower, {}), time)
        _, tx, ty, _, _ = _local(bones[tip], tracks.get(tip, {}), time)
        chains.append((parent, pose[upper][4:6], ua, usx, usy, la, lx, ly, tx*lsx, ty*lsy, target))

    def endpoints(values):
        points = []
        for i, (p, origin, ua, sx, sy, la, lx, ly, tx, ty, _) in enumerate(chains):
            du, dl = (math.degrees(v) for v in values[2+i*2:4+i*2])
            rx, ry = _rotate(la+dl, (tx, ty))
            vx, vy = _rotate(ua+du, (sx*(lx+rx), sy*(ly+ry)))
            points.append([origin[0]+p[0]*vx+p[1]*vy+reference_length*values[0],
                           origin[1]+p[2]*vx+p[3]*vy+reference_length*values[1]])
        return points

    def objective(values):
        error = sum(math.dist(point, chain[-1])**2 for point, chain in zip(endpoints(values), chains))
        continuity = float(np.dot(values[:2]-previous_root, values[:2]-previous_root)) if previous_root is not None else 0
        if preserve_pose:
            from .support_pose_objective import loss
            return loss(chains, values) + 1e-8*float(np.dot(values, values)) + 1e-8*continuity
        return error/reference_length**2 + 1e-8*float(np.dot(values, values)) + 1e-8*continuity

    size = 2+2*len(chains)
    seed = np.zeros(size)
    initial = endpoints(seed)
    desired = np.mean([(np.asarray(c[-1])-p)/reference_length for p, c in zip(initial, chains)], axis=0)
    desired *= min(1., .15/max(1e-12, float(np.linalg.norm(desired))))
    other = np.zeros(size); other[:2] = desired
    if previous_root is not None:
        seed[:2] = previous_root
        other[:2] = previous_root
    limit = math.radians(maximum_degrees)
    bounds = [(-.15, .15)]*2 + [(-limit, limit)]*(size-2)
    if maximum_rotation_speed is not None and previous is not None:
        prior_legs = {r['upper']: r for r in previous.get('legs', [])}
        for i, contact in enumerate(contacts):
            prior = prior_legs.get(contact['upper'])
            if prior is None:
                continue  # Entry and release still need their own transition QA.
            if prior['lower'] != contact['lower'] or prior['tip'] != contact['tip']:
                raise ValueError('joint_support_previous_chain_changed')
            for j, key in enumerate(('upper_delta_degrees', 'lower_delta_degrees')):
                value = math.radians(prior[key])
                if not math.isfinite(value) or abs(value) > limit+1e-9:
                    raise ValueError('joint_support_previous_rotation_invalid')
                radius = math.radians(maximum_rotation_speed*elapsed)*.99999
                bounds[2+i*2+j] = (max(-limit, value-radius), min(limit, value+radius))
                seed[2+i*2+j] = other[2+i*2+j] = value
    trials = []
    constraints = [dict(type='ineq', fun=lambda x: .15**2-float(np.dot(x[:2], x[:2])))]
    if preserve_pose:
        # Normalized exact endpoint equations avoid near-zero squared-distance
        # gradients. Independent residual checks below still enforce the gate.
        constraints.append(dict(type='eq', fun=lambda x: np.asarray([
            (p[j]-c[-1][j])/reference_length
            for p, c in zip(endpoints(x), chains) for j in (0, 1)])))
    if previous_root is not None:
        # Leave numerical headroom, then enforce the actual speed bound without
        # tolerance. Tiny time gaps amplify even nanometre constraint overshoot.
        constraints.append(dict(type='ineq', fun=lambda x: (step_limit*.99999)**2-float(np.dot(x[:2]-previous_root, x[:2]-previous_root))))
    for start in (seed, other):
        result = minimize(objective, start, method='SLSQP', bounds=bounds,
                          constraints=constraints,
                          options=dict(maxiter=200, ftol=1e-13))
        # SLSQP may return a value one ULP beyond a bound. Clamp the actual
        # proposed parameters, then recompute FK/residual; never relax the gate.
        values = (np.clip(result.x, [b[0] for b in bounds], [b[1] for b in bounds])
                  if maximum_rotation_speed is not None else result.x)
        if not np.isfinite(values).all(): continue
        if maximum_rotation_speed is not None:
            # Project numerical optimizer overshoot into the two convex root
            # disks. Finite iterations are not assumed feasible: gates below
            # independently verify both disks and recomputed endpoint residual.
            disks = [(np.zeros(2), .15*.99999999)]
            if previous_root is not None: disks.append((previous_root, step_limit*.99999))
            for _ in range(16):
                for center, radius in disks:
                    delta = values[:2]-center; distance = float(np.linalg.norm(delta))
                    if distance > radius: values[:2] = center+delta*(radius/distance)
        errors = [math.dist(point, c[-1]) for point, c in zip(endpoints(values), chains)]
        checks = dict(root_displacement=np.linalg.norm(values[:2]) <= .15+1e-9,
                      rotation_magnitude=max(abs(v) for v in values[2:]) <= limit+1e-9,
                      rotation_speed=maximum_rotation_speed is None or all(lo <= value <= hi for value, (lo, hi) in zip(values[2:], bounds[2:])),
                      root_speed=previous_root is None or np.linalg.norm(values[:2]-previous_root) <= step_limit,
                      endpoint_residual=max(errors) <= residual_limit)
        valid = all(checks.values())
        trials.append(dict(valid=bool(valid), values=values, errors=errors, objective=objective(values),
                           failed_checks=[k for k, passed in checks.items() if not passed],
                           solver_success=bool(result.success), iterations=int(result.nit)))
    best = min(trials, key=lambda r: (not r['valid'], r['objective']), default=None)
    solution = None
    if best and best['valid']:
        v = best['values']
        solution = dict(root_shift=[float(x)*reference_length for x in v[:2]],
            legs=[dict(upper=c['upper'], lower=c['lower'], tip=c['tip'],
                       upper_delta_degrees=math.degrees(v[2+i*2]), lower_delta_degrees=math.degrees(v[3+i*2]),
                       endpoint_error_px=best['errors'][i]) for i, c in enumerate(contacts)])
    return dict(profile='joint-root-source-axis-support-v1-experiment' if preserve_pose else
                'joint-root-affine-leg-support-v2' if maximum_rotation_speed is not None else 'joint-root-affine-leg-support-v1', selected=False, authority='none',
                status='candidate' if solution else 'no_bounded_solution_found', solution=solution,
                best_errors_px=best['errors'] if best else [],
                failed_checks=best['failed_checks'] if best else ['nonfinite_solver_result'],
                scope='single_time_endpoints_not_temporal_mesh_or_runtime_validation',
                limits=dict(root_ratio=.15, rotation_degrees=maximum_degrees,
                            residual_ratio=.01 if maximum_error_px is None else residual_limit/reference_length,
                            root_speed_ratio=2 if previous is not None else None,
                            rotation_speed_degrees_per_second=maximum_rotation_speed))
