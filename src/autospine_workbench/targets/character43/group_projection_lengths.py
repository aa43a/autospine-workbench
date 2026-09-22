"""Smallest source-bounded length blend satisfying the endpoint triangle."""
import math
from .group_projection_constraints import preserve_ankles


def feasible_lengths(projected, source, distance):
    if (len(projected) != 2 or len(source) != 2 or
            any(not math.isfinite(v) or v <= 0 for v in (*projected, *source, distance)) or
            any(a > b+1e-8 for a, b in zip(projected, source))):
        raise ValueError('group_length_bounds_invalid')
    p, q = projected
    a, b = (source[i]-projected[i] for i in (0, 1))
    low, high = 0., 1.
    # Intersect linear halfspaces c + slope*t >= 0.
    for c, slope in ((p+q-distance, a+b), (distance-p+q, -a+b), (distance+p-q, a-b)):
        if abs(slope) < 1e-12:
            if c < -1e-9: return None
        elif slope > 0:
            low = max(low, -c/slope)
        else:
            high = min(high, -c/slope)
    if low > high+1e-12: return None
    blend = min(1., max(0., low))
    return [p+a*blend, q+b*blend], blend


def constrain(original, projected, source_segments, frame, sign):
    lengths, changes = {}, []
    for side in ('left', 'right'):
        roles = [f'humanoid.leg.{part}.{side}' for part in ('upper', 'lower')]
        values = [math.dist(projected[r]['start'], projected[r]['end']) for r in roles]
        bounds = [math.sqrt(sum(v*v for v in source_segments[r][frame][1])) for r in roles]
        distance = math.dist(projected[roles[0]]['start'], original[roles[1]]['end'])
        solution = feasible_lengths(values, bounds, distance)
        lengths[side] = solution[0] if solution else values
        changes.append(dict(side=side, feasible=solution is not None,
            blend=solution[1] if solution else None, projected_lengths=values,
            source_bounds=bounds, output_lengths=lengths[side]))
    result, failures = preserve_ankles(original, projected, sign, lengths=lengths)
    return result, failures, changes


def continuity(frames, times):
    records = []
    for side in ('left', 'right'):
        role = f'humanoid.leg.upper.{side}'
        angles = [math.degrees(math.atan2(f[role]['end'][1]-f[role]['start'][1],
                                         f[role]['end'][0]-f[role]['start'][0])) for f in frames]
        steps = [abs((b-a+180)%360-180) for a, b in zip(angles, angles[1:])]
        peak = max(range(len(steps)), key=steps.__getitem__)
        records.append(dict(side=side, maximum_sample_angle_step=steps[peak], time=times[peak+1],
            maximum_sample_angular_speed=max(v/(b-a) for v, a, b in zip(steps, times, times[1:]))))
    return dict(scope='sampled_upper_leg_angles_not_mesh_or_visual_acceptance', records=records)
