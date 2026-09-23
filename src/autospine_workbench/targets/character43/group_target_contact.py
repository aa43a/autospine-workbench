"""Experimental target-space ankle preservation after directional retargeting."""
from copy import deepcopy
import math
from .affine_leg_ik import solve
from .affine_pose import matrices
from .group_bend_evidence import evidence


def _bend(pose, upper, lower, tip):
    a, b, c = [pose[name][4:6] for name in (upper, lower, tip)]
    return evidence([b[0]-a[0], a[1]-b[1], 0], [c[0]-b[0], b[1]-c[1], 0], 0)


def constrain(candidate, reference, times):
    result = deepcopy(candidate)
    tracks = result['animations']['external-motion']['bones']
    records = []
    for index, time in enumerate(times):
        target_pose = matrices(reference, 'external-motion', time)
        for side in ('l', 'r'):
            upper, lower, tip = 'thigh_'+side, 'calf_'+side, 'foot_'+side
            for bone in (upper, lower):
                if tracks[bone]['rotate'][index]['time'] != time:
                    raise ValueError('group_target_time_identity_mismatch')
            target = target_pose[tip][4:6]
            before_bend = _bend(matrices(result, 'external-motion', time), upper, lower, tip)
            solved = solve(result, 'external-motion', time, upper, lower, tip, target, maximum_degrees=90)
            change = solved['solution']
            if change:
                for part, bone in (('upper', upper), ('lower', lower)):
                    tracks[bone]['rotate'][index]['value'] += change[part+'_delta_degrees']
            after = matrices(result, 'external-motion', time)
            after_bend = _bend(after, upper, lower, tip)
            bend_status = ('unknown' if None in (before_bend['branch'], after_bend['branch']) else
                           'preserved' if before_bend['branch'] == after_bend['branch'] else 'changed')
            records.append(dict(time=time, side=side, status=solved['status'],
                endpoint_error_px=math.dist(after[tip][4:6], target), correction=change,
                bend_before=before_bend, bend_after=after_bend, bend_status=bend_status,
                exceeds_outer_reach_bound=solved['exceeds_outer_reach_bound']))
    # Keep interpolation on the same angle branch; this does not alter key poses.
    for bone in ('thigh_l', 'calf_l', 'thigh_r', 'calf_r'):
        keys = tracks[bone]['rotate']
        for previous, key in zip(keys, keys[1:]):
            key['value'] = previous['value']+(key['value']-previous['value']+180)%360-180
    return result, dict(profile='target-ankle-preservation-after-group-fit-v1-experiment',
        authority='none', selected=False, records=records,
        failures=sum(r['status'] != 'candidate' for r in records),
        bend_branch_changes=sum(r['bend_status'] == 'changed' for r in records),
        bend_branch_unknown=sum(r['bend_status'] == 'unknown' for r in records),
        maximum_endpoint_error_px=max(r['endpoint_error_px'] for r in records),
        scope='source_keys_only_interpolation_mesh_and_contact_need_validation')
