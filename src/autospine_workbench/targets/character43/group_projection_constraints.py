"""Diagnostic endpoint constraints on source skeletons, without target adoption."""
from copy import deepcopy
import math


def circle_joint(start, end, upper, lower, sign):
    if sign not in (-1, 1) or min(upper, lower) <= 0:
        raise ValueError('group_joint_parameters_invalid')
    distance = math.dist(start, end)
    if distance < 1e-9 or distance > upper+lower+1e-9 or distance < abs(upper-lower)-1e-9:
        return None  # No clamping or silent bone stretching.
    along = (upper*upper-lower*lower+distance*distance)/(2*distance)
    height = math.sqrt(max(0., upper*upper-along*along))
    x, y = ((end[i]-start[i])/distance for i in (0, 1))
    return [start[0]+along*x-sign*height*y, start[1]+along*y+sign*height*x]


def preserve_ankles(original, projected, sign):
    result = deepcopy(projected)
    failures = []
    for side in ('left', 'right'):
        upper, lower = (f'humanoid.leg.{part}.{side}' for part in ('upper', 'lower'))
        a, b = result[upper], result[lower]
        end = original[lower]['end']
        joint = circle_joint(a['start'], end, math.dist(a['start'], a['end']),
                             math.dist(b['start'], b['end']), sign)
        if joint is None:
            failures.append(dict(side=side, reason='projected_lengths_cannot_reach_original_ankle'))
            continue
        a['end'], b['start'], b['end'] = joint, joint, list(end)
        foot = f'humanoid.leg.foot.{side}'
        if foot in result:
            delta = [end[i]-result[foot]['start'][i] for i in (0, 1)]
            result[foot]['start'] = list(end)
            result[foot]['end'] = [result[foot]['end'][i]+delta[i] for i in (0, 1)]
    return result, failures


def measure(original, candidate, times):
    records = []
    for limb in ('arm', 'leg'):
        for side in ('left', 'right'):
            role = f'humanoid.{limb}.lower.{side}'
            initial = [candidate[0][role]['end'][i]-original[0][role]['end'][i] for i in (0, 1)]
            offsets = [[b[role]['end'][i]-a[role]['end'][i] for i in (0, 1)]
                       for a, b in zip(original, candidate)]
            errors = [math.hypot(*(v[i]-initial[i] for i in (0, 1))) for v in offsets]
            scale = sum(math.dist(original[0][f'humanoid.{limb}.{part}.{side}']['start'],
                                 original[0][f'humanoid.{limb}.{part}.{side}']['end']) for part in ('upper', 'lower'))
            peak = max(range(len(errors)), key=errors.__getitem__)
            records.append(dict(group=f'{limb}.{side}', maximum_endpoint_offset=max(math.hypot(*v) for v in offsets),
                maximum_added_motion=errors[peak], added_motion_over_initial_projected_chain=errors[peak]/scale if scale else None,
                peak_time=times[peak]))
    return dict(authority='none', scope='source_endpoint_difference_not_foot_sole_contact', records=records)
