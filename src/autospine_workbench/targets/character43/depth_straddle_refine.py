"""Experimental held-order refinement; uncertain pixels never change authority."""
from copy import deepcopy
from .mesh_depth_proxy import overlap_support, CAP_PROFILE
from .motion_depth_overlap import Probe

PROFILE='local-depth-held-order-refinement-v1'


def refine(document,files,animation,depth,sampler,*,torso_plane=False,rendered_bounds=False,order_probe=None,tiled=False,pair_budgets=False,sparse=False,sleeve_helpers=None,plane_provider=None):
    if plane_provider is not None and not torso_plane:
        raise ValueError('depth_refinement_plane_requires_torso_model')
    candidate=deepcopy(depth)
    probe=Probe(document,files,animation,rendered_bounds=rendered_bounds,tiled=tiled,sparse=sparse)
    if order_probe is not None: order_probe.reuse(probe)
    ticks=sorted({r['tick'] for p in depth['pairs'] for r in p['samples']})
    if pair_budgets and (len(depth['pairs'])>16 or len(ticks)>512):
        raise ValueError('depth_refinement_pair_resource_limit')
    next_tick=dict(zip(ticks,ticks[1:]))
    evidence=dict(profile=PROFILE,proxy_profile=CAP_PROFILE,authority='none',selected=False,
                  rows=[],scope='source_frame_and_midpoint_model_not_continuous_time_or_visual_acceptance')
    checker=None
    budgets=[]; reused=0; axes={}
    if torso_plane:
        from .torso_depth_refinement import Checker,PROFILE as TORSO_PROFILE
        checker=Checker(probe,sampler,sleeve_helpers=sleeve_helpers,plane_provider=plane_provider)
        evidence.update(profile=TORSO_PROFILE,proxy_profile=TORSO_PROFILE,
            assumptions=['planar_torso','mesh_hand_axis_to_source_fingertip','same_arm_secondary_influence_envelope'])
        if plane_provider is not None:
            evidence['torso_plane_source']='explicit_provider_not_unwarped_bones'
    for pair in candidate['pairs']:
        if pair_budgets:
            probe=Probe(document,files,animation,rendered_bounds=rendered_bounds,tiled=tiled,sparse=sparse)
            if torso_plane: checker=Checker(probe,sampler,sleeve_helpers=sleeve_helpers,plane_provider=plane_provider)
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
        if pair_budgets:
            budgets.append(dict(pair=[arm,body],pixel_budget_used=64_000_000-probe.remaining))
            if checker is not None: axes.update(checker.axes)
            if order_probe is not None: reused+=order_probe.reuse(probe)
    candidate['ambiguous_pair_samples']=sum(r['ambiguous'] for p in candidate['pairs'] for r in p['samples'])
    if 'target_overlap' in candidate:
        candidate['target_overlap']['ambiguous_visible_pair_samples']=sum(
            r['ambiguous'] and r.get('overlap',{}).get('overlap_pixels',0)>0
            for p in candidate['pairs'] for r in p['samples'])
    evidence['resolved_rows']=sum(r['resolved'] for r in evidence['rows'])
    evidence['remaining_rows']=len(evidence['rows'])-evidence['resolved_rows']
    evidence['pixel_budget_used']=64_000_000-probe.remaining
    if rendered_bounds: evidence['bounds_policy']='rendered_triangle_vertices'
    if checker is not None: evidence['hand_mesh_axes']=checker.axes
    if order_probe is not None: evidence['reused_order_overlap_samples']=order_probe.reuse(probe)
    if pair_budgets:
        evidence.update(resource_profile='per_pair_refinement_budget_v1',pair_budgets=budgets,
            pixel_budget_used=sum(b['pixel_budget_used'] for b in budgets),pixel_budget_per_pair=64_000_000,
            max_pairs=16,max_source_frames=512)
        if checker is not None: evidence['hand_mesh_axes']=axes
        if order_probe is not None: evidence['reused_order_overlap_samples']=reused
    candidate['local_depth_refinement']=evidence
    return candidate,evidence
