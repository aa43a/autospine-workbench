"""Optional declared-Mixamo palm depth; never infer an absent fingertip."""
PROFILE = 'mixamo-wrist-middle-knuckle-depth-v1-experiment'


def observe(sampler, tick, *, full_hand=False):
    result = dict(profile=PROFILE, segments={}, joints={}, authority='none', selected=False,
                  assumption='target_hand_axis_corresponds_to_source_wrist_middle_knuckle_segment')
    if sampler.mapping.get('map_id') != 'mixamo-declared-body-v1':
        return result
    depths = sampler.joint_depths(tick,include_end_sites=True) if full_hand else sampler.joint_depths(tick)
    if full_hand:
        result.update(profile='mixamo-wrist-middle-fingertip-depth-v1-experiment',
                      assumption='target_hand_axis_corresponds_to_source_wrist_middle_fingertip_chord')
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
        chain=[wrist,knuckle]; endpoint=knuckle
        if full_hand:
            chain += [wrist+'Middle2',wrist+'Middle3']
            if any(n not in sampler.indices for n in chain): continue
            if any(sampler.bvh.joints[sampler.indices[b]].parent_index!=sampler.indices[a]
                   for a,b in zip(chain,chain[1:])): continue
            endpoint=(chain[-1],'end_site')
            if endpoint not in depths: continue
            chain.append(chain[-1]+':EndSite')
        result['segments']['hand_'+suffix] = (depths[wrist],depths[endpoint])
        result['joints']['hand_'+suffix] = chain
    return result
