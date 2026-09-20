"""Experimental held-order refinement; uncertain pixels never change authority."""
from copy import deepcopy
from .mesh_depth_proxy import overlap_support, CAP_PROFILE
from .motion_depth_overlap import Probe

PROFILE='local-depth-held-order-refinement-v1'


def refine(document,files,animation,depth,sampler,*,torso_plane=False):
    candidate=deepcopy(depth)
    probe=Probe(document,files,animation)
    ticks=sorted({r['tick'] for p in depth['pairs'] for r in p['samples']})
    next_tick=dict(zip(ticks,ticks[1:]))
    evidence=dict(profile=PROFILE,proxy_profile=CAP_PROFILE,authority='none',selected=False,
                  rows=[],scope='source_frame_and_midpoint_model_not_continuous_time_or_visual_acceptance')
    checker=None
    if torso_plane:
        from .torso_depth_refinement import Checker,PROFILE as TORSO_PROFILE
        checker=Checker(probe,sampler)
        evidence.update(profile=TORSO_PROFILE,proxy_profile=TORSO_PROFILE,
            assumptions=['planar_torso','mesh_hand_axis_to_source_fingertip','same_arm_secondary_influence_envelope'])
    for pair in candidate['pairs']:
        arm,body=pair['arm_slot'],pair['torso_slot']
        for row in pair['samples']:
            if not row['ambiguous']:
                continue
            tick=row['tick']; times=[tick]
            if tick in next_tick: times.append((tick+next_tick[tick])/2)
            checks=[]; supported=True; visible=False
            for point in times:
                try:
                    if checker is not None:
                        result=checker.check(arm,body,point/1e6,row['source_tick']+point-tick)
                    else:
                        segments=sampler(row['source_tick']+point-tick)
                        result=overlap_support(probe,arm,body,point/1e6,segments,endpoint_caps=True)
                except ValueError as exc:
                    result=dict(status='unmeasured',reason_code=str(exc),time=point/1e6)
                checks.append(result)
                if result['status']=='no_overlap': continue
                visible=True
                expected='uniform_front_proxy' if row['current_front_slot']==arm else 'uniform_back_proxy'
                if result['status']!=expected: supported=False
            resolved=supported and visible
            if resolved: row['ambiguous']=False
            evidence['rows'].append(dict(pair=[arm,body],tick=tick,source_tick=row['source_tick'],
                                         resolved=resolved,checks=checks))
    candidate['ambiguous_pair_samples']=sum(r['ambiguous'] for p in candidate['pairs'] for r in p['samples'])
    if 'target_overlap' in candidate:
        candidate['target_overlap']['ambiguous_visible_pair_samples']=sum(
            r['ambiguous'] and r.get('overlap',{}).get('overlap_pixels',0)>0
            for p in candidate['pairs'] for r in p['samples'])
    evidence['resolved_rows']=sum(r['resolved'] for r in evidence['rows'])
    evidence['remaining_rows']=len(evidence['rows'])-evidence['resolved_rows']
    evidence['pixel_budget_used']=64_000_000-probe.remaining
    if checker is not None: evidence['hand_mesh_axes']=checker.axes
    candidate['local_depth_refinement']=evidence
    return candidate,evidence
