"""Optional declared-Mixamo palm depth; never infer an absent fingertip."""
PROFILE = 'mixamo-wrist-middle-knuckle-depth-v1-experiment'


def observe(sampler, tick):
    result = dict(profile=PROFILE, segments={}, joints={}, authority='none', selected=False,
                  assumption='target_hand_axis_corresponds_to_source_wrist_middle_knuckle_segment')
    if sampler.mapping.get('map_id') != 'mixamo-declared-body-v1':
        return result
    depths = sampler.joint_depths(tick)
    for side, suffix, expected in [('left','l','LeftHand'),('right','r','RightHand')]:
        role = sampler.roles.get('humanoid.arm.lower.'+side, {})
        wrist = role.get('aim', {}).get('joint_name', '')
        if wrist not in (expected, 'mixamorig:'+expected):
            continue
        knuckle = wrist+'Middle1'
        if wrist not in sampler.indices or knuckle not in sampler.indices:
            continue
        joint = sampler.bvh.joints[sampler.indices[knuckle]]
        if joint.parent_index != sampler.indices[wrist]:
            continue
        result['segments']['hand_'+suffix] = (depths[wrist],depths[knuckle])
        result['joints']['hand_'+suffix] = [wrist,knuckle]
    return result
