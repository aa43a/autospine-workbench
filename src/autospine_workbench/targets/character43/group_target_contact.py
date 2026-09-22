"""Experimental target-space ankle preservation after directional retargeting."""
from copy import deepcopy
import math
from .affine_leg_ik import solve
from .affine_pose import matrices


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
            solved = solve(result, 'external-motion', time, upper, lower, tip, target, maximum_degrees=90)
            change = solved['solution']
            if change:
                for part, bone in (('upper', upper), ('lower', lower)):
                    tracks[bone]['rotate'][index]['value'] += change[part+'_delta_degrees']
            after = matrices(result, 'external-motion', time)
            records.append(dict(time=time, side=side, status=solved['status'],
                endpoint_error_px=math.dist(after[tip][4:6], target), correction=change,
                exceeds_outer_reach_bound=solved['exceeds_outer_reach_bound']))
    # Keep interpolation on the same angle branch; this does not alter key poses.
    for bone in ('thigh_l', 'calf_l', 'thigh_r', 'calf_r'):
        keys = tracks[bone]['rotate']
        for previous, key in zip(keys, keys[1:]):
            key['value'] = previous['value']+(key['value']-previous['value']+180)%360-180
    return result, dict(profile='target-ankle-preservation-after-group-fit-v1-experiment',
        authority='none', selected=False, records=records,
        failures=sum(r['status'] != 'candidate' for r in records),
        maximum_endpoint_error_px=max(r['endpoint_error_px'] for r in records),
        scope='source_keys_only_interpolation_mesh_and_contact_need_validation')
