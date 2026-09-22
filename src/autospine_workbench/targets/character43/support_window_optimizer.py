"""Bounded, fixed-end temporal support optimization; experimental and opt-in."""
import math
from copy import deepcopy
from .support_window_model import prepare, evaluate


def optimize(document, name, rows, anchors, reference, *, extra_times=(), preserve_endpoint=False):
    import numpy as np
    from scipy.optimize import minimize
    if type(preserve_endpoint) is not bool:
        raise ValueError('support_window_endpoint_mode_invalid')
    if not 5 <= len(rows) <= 65 or not math.isfinite(reference) or reference <= 0:
        raise ValueError('support_window_size_invalid')
    names = ('thigh_l', 'calf_l', 'thigh_r', 'calf_r')
    knots = np.asarray([r['time'] for r in rows])
    if not np.isfinite(knots).all() or np.any(np.diff(knots) <= 0):
        raise ValueError('support_window_times_invalid')
    targets = []
    for side in ('left', 'right'):
        active = [a for a in anchors if a['limb'] == 'leg.'+side and a['start'] <= knots[0] and a['end'] > knots[-1]]
        if len(active) != 1:
            raise ValueError('support_window_constant_double_support_required')
        targets.append(active[0]['target'])
    targets = np.asarray(targets)
    seed = np.asarray([[*np.asarray(r['root_shift'])/reference,
                        *[math.radians(r['angles'][n]) for n in names]] for r in rows])
    if not np.isfinite(seed).all() or targets.shape != (2, 2) or not np.isfinite(targets).all():
        raise ValueError('support_window_values_invalid')
    extra = np.asarray(extra_times,dtype=float)
    if extra.ndim!=1 or len(extra)>4097 or not np.isfinite(extra).all() or np.any(extra<knots[0]) or np.any(extra>knots[-1]):
        raise ValueError('support_window_extra_times_invalid')
    times = np.unique(np.concatenate((knots, (knots[:-1]+knots[1:])/2, extra)))
    base = np.column_stack([np.interp(times, knots, seed[:, i]) for i in range(6)])
    controls = np.unique(np.linspace(0, len(knots)-1, 9).round().astype(int))
    control_times = knots[controls]
    model = prepare(document, name, times)
    source_points, source_axes = evaluate(model, np.zeros_like(base), reference)
    old_points, _ = evaluate(model, base, reference)
    def endpoint_error(values):
        points, _ = evaluate(model, values, reference)
        # Compare hip-relative endpoints: root translation is not limb fidelity.
        return np.linalg.norm(points-reference*values[:,None,:2]-source_points,axis=2)
    endpoint_limit=np.maximum(endpoint_error(base),1e-6)
    contact_limit = float(np.max(np.linalg.norm(old_points-targets, axis=2)))
    # Preserve measured baseline precision. A tiny numeric floor is explicit.
    residual = max(contact_limit, 1e-6)
    dt = np.diff(times)

    def unpack(x):
        offsets = np.zeros((len(controls), 6)); offsets[1:-1] = x.reshape(-1, 6)
        return base+np.column_stack([np.interp(times, control_times, offsets[:, i]) for i in range(6)])

    def objective(x):
        _, axes = evaluate(model, unpack(x), reference)
        delta = (axes-source_axes+np.pi) % (2*np.pi)-np.pi
        return float(np.mean(delta**2))

    def measures(values):
        points, _ = evaluate(model, values, reference)
        root_speed = np.linalg.norm(np.diff(values[:, :2], axis=0), axis=1)/dt
        rotation_speed = np.max(abs(np.diff(values[:, 2:], axis=0)), axis=1)/dt
        return (np.linalg.norm(points-targets, axis=2), np.linalg.norm(values[:, :2], axis=1),
                np.max(abs(values[:, 2:]), axis=1), root_speed, rotation_speed)

    def constraints(x):
        errors, roots, angles, rs, speed = measures(unpack(x))
        result=np.concatenate(((1-errors/residual).ravel(), 1-roots/.15,
                               1-angles/(np.pi/6), 1-rs/2, 1-speed/np.pi))
        if preserve_endpoint:
            result=np.concatenate((result,(1-endpoint_error(unpack(x))/endpoint_limit).ravel()))
        return result

    zero = np.zeros((len(controls)-2)*6)
    before = objective(zero)
    report = dict(profile='fixed-end-source-axis-window-v1-experiment', authority='none', selected=False,
                  start=float(knots[0]), end=float(knots[-1]), samples=len(times),
                  baseline_loss=before, baseline_contact_px=contact_limit, residual_limit_px=residual)
    if len(extra):
        report.update(profile='fixed-end-source-axis-feedback-window-v1-experiment', feedback_samples=len(extra))
    if preserve_endpoint:
        report.update(profile='fixed-end-source-axis-endpoint-guard-v1-experiment',
                      baseline_endpoint_error_px=float(endpoint_error(base).max()),
                      endpoint_guard='per_sample_per_leg_hip_relative_no_regression',endpoint_floor_px=1e-6,
                      endpoint_check_times=times.tolist())
    report['baseline_minimum_constraint'] = float(np.min(constraints(zero)))
    if np.min(constraints(zero)) < -1e-7:
        return rows, dict(report, status='baseline_constraints_failed')
    # Reserve solver headroom at movable samples; fixed endpoints retain their
    # exact reference values and are independently checked by the original gates.
    margin = np.full(len(constraints(zero)), 1e-6)
    count = len(times)
    margin[[0, 1, 2*count-2, 2*count-1, 2*count, 3*count-1, 3*count, 4*count-1]] = 0
    if preserve_endpoint:
        # Fixed endpoints cannot improve. Movable samples reserve the same
        # solver headroom as contact constraints; the final gate stays exact.
        margin[[-2*count,-2*count+1,-2,-1]]=0
    result = minimize(objective, zero, method='SLSQP', constraints=[dict(type='ineq', fun=lambda x:constraints(x)-margin)],
                      options=dict(maxiter=150, ftol=1e-10))
    values_result = result.x
    finite = np.isfinite(values_result).all()
    report['optimizer_minimum_constraint'] = float(np.min(constraints(values_result))) if finite else None
    valid = False; fraction = None
    if finite:
        # Backtrack toward the verified reference trajectory; do not relax any gate.
        for step in (1., .999, .99, .95, .9, .75, .5, .25):
            trial = result.x*step
            if np.min(constraints(trial)) >= 0:
                values_result = trial; valid = True; fraction = step; break
    after = objective(values_result) if finite else before
    if preserve_endpoint and finite:
        errors=endpoint_error(unpack(values_result))
        report.update(candidate_endpoint_error_px=float(errors.max()),
                      maximum_endpoint_regression_px=float(np.max(errors-endpoint_limit)))
    report.update(status='candidate' if valid and after < before-1e-10 else 'no_improving_window_found',
                  candidate_loss=after, iterations=int(result.nit), optimizer_success=bool(result.success),
                  accepted_step_fraction=fraction)
    if report['status'] != 'candidate':
        return rows, report
    values = unpack(values_result)
    report['maximum_contact_px'] = float(measures(values)[0].max())
    output = []
    for t in knots:
        v = values[np.searchsorted(times, t)]
        output.append(dict(time=float(t), root_shift=(v[:2]*reference).tolist(),
                           angles={n: math.degrees(a) for n, a in zip(names, v[2:])}))
    output[0] = deepcopy(rows[0]); output[-1] = deepcopy(rows[-1])
    return output, report
