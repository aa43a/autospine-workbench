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


def constrain(original, projected, source_segments, frame, sign, *, length_mode='minimum_blend'):
    if length_mode not in ('minimum_blend', 'source_lengths'):
        raise ValueError('group_length_mode_invalid')
    lengths, changes = {}, []
    for side in ('left', 'right'):
        roles = [f'humanoid.leg.{part}.{side}' for part in ('upper', 'lower')]
        values = [math.dist(projected[r]['start'], projected[r]['end']) for r in roles]
        bounds = [math.sqrt(sum(v*v for v in source_segments[r][frame][1])) for r in roles]
        distance = math.dist(projected[roles[0]]['start'], original[roles[1]]['end'])
        solution = feasible_lengths(values, bounds, distance)
        if length_mode == 'source_lengths':
            solution = (bounds, 1.) if abs(bounds[0]-bounds[1]) <= distance <= sum(bounds) else None
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
            steps=steps,
            maximum_sample_angular_speed=max(v/(b-a) for v, a, b in zip(steps, times, times[1:]))))
    return dict(scope='sampled_upper_leg_angles_not_mesh_or_visual_acceptance', records=records)


def source_continuity(segments, times):
    records = []
    for side in ('left', 'right'):
        role = f'humanoid.leg.upper.{side}'
        vectors = [row[1] for row in segments[role]]
        steps = [math.degrees(math.acos(max(-1., min(1.,
            sum(x*y for x, y in zip(a, b))/(math.hypot(*a)*math.hypot(*b))))))
            for a, b in zip(vectors, vectors[1:])]
        peak = max(range(len(steps)), key=steps.__getitem__)
        records.append(dict(side=side, maximum_source_3d_step_degrees=steps[peak],
                            time=times[peak+1], steps=steps))
    return dict(scope='source_upper_leg_3d_direction_changes_no_target_inference', records=records)


def compare_continuity(candidate, source, times):
    records = []
    for row, baseline in zip(candidate['records'], source['records']):
        if row['side'] != baseline['side'] or len(row['steps']) != len(baseline['steps']):
            raise ValueError('continuity_source_mismatch')
        differences = [max(0., a-b) for a, b in zip(row['steps'], baseline['steps'])]
        peak = max(range(len(differences)), key=differences.__getitem__)
        records.append(dict(side=row['side'], maximum_excess_step_degrees=differences[peak],
            time=times[peak+1], candidate_step=row['steps'][peak], source_3d_step=baseline['steps'][peak]))
    return dict(scope='step_magnitude_comparison_not_equivalent_3d_2d_motion', records=records)
