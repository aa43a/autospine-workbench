"""Full-clip experimental arm/garment constraints from bounded depth models."""
from copy import deepcopy
from .cloth_depth_plane import at
from .hand_depth_observation import observe
from .hand_mesh_axis import infer
from .weighted_depth_interval import build as interval_build
from .mesh_depth_proxy import overlap_support
from .motion_depth_overlap import Probe
from ..spine43.seam_raster import texture

PROFILE = 'full-clip-planar-garment-interval-order-v1-experiment'


def held_front(checks, arm, cloth, fallback):
    statuses={c['status'] for c in checks if c['status']!='no_overlap'}
    if not statuses: return fallback,False
    if statuses=={'uniform_front_proxy'}: return arm,False
    if statuses=={'uniform_back_proxy'}: return cloth,False
    return fallback,True


def build(document, files, animation, depth, partition, sampler, *, order_probe=None,sleeve_helpers=None):
    if order_probe is not None and (order_probe.document is not document or order_probe.files is not files
                                    or order_probe.animation!=animation):
        raise ValueError('cloth_constraint_probe_identity')
    result=deepcopy(depth)
    arms=depth['groups']['left']+depth['groups']['right']
    clothes=[r['slot'] for r in partition['regions'] if r['group'] in ('mixed','unmapped')]
    if not clothes or len(arms)*len(clothes)>16:
        raise ValueError('cloth_constraint_pair_limit')
    index={s['name']:i for i,s in enumerate(document['slots'])}
    slots={s['name']:s for s in document['slots']}
    source={r['tick']:r['source_tick'] for p in depth['pairs'] for r in p['samples']}
    ticks=sorted(source)
    if not ticks or len(ticks)>512: raise ValueError('cloth_constraint_frame_limit')
    if any(source[r['tick']]!=r['source_tick'] for p in depth['pairs'] for r in p['samples']):
        raise ValueError('cloth_constraint_source_time_mismatch')
    following=dict(zip(ticks,ticks[1:])); models={}; axes={}; evidence=[]
    for arm in arms:
        slot=slots[arm]; mesh=document['skins'][0]['attachments'][arm][slot['attachment']]
        axes[arm]=infer(document,mesh,texture(files['images/'+mesh.get('path',slot['attachment'])+'.png']))
    for arm in arms:
        mesh=document['skins'][0]['attachments'][arm][slots[arm]['attachment']]
        for cloth in clothes:
            probe=Probe(document,files,animation,rendered_bounds=bool(order_probe and order_probe.rendered_bounds),
                        tiled=bool(order_probe and order_probe.tiled),sparse=order_probe.sparse if order_probe else False)
            fallback=max((arm,cloth),key=index.__getitem__); samples=[]; details=[]
            for tick in ticks:
                times=[tick]+([(tick+following[tick])/2] if tick in following else [])
                checks=[]
                for point in times:
                    time=point/1e6; source_tick=source[tick]+point-tick
                    try:
                        pair=probe.pair(arm,cloth,time)
                        if not pair['overlap_pixels']:
                            check=dict(status='no_overlap',time=time)
                        else:
                            if point not in models:
                                plane=at(document,animation,time,sampler,source_tick)
                                segments=sampler(source_tick); hands=observe(sampler,source_tick,full_hand=True)
                                segments.update(hands['segments'])
                                models[point]=(plane,segments,hands)
                            plane,segments,hands=models[point]
                            lengths={n:v['length'] for n,v in axes[arm]['axes'].items() if n in hands['segments']}
                            intervals=interval_build(document,mesh,segments,axis_lengths=lengths)
                            if sleeve_helpers:
                                from .sleeve_depth_intervals import at as sleeve_intervals
                                intervals=sleeve_intervals(probe,sampler,source_tick,arm,time,segments,sleeve_helpers,axis_lengths=lengths)
                            check=overlap_support(probe,arm,cloth,time,segments,endpoint_caps=True,
                                reference_plane=plane['coefficients'],axis_lengths=lengths,depth_intervals=intervals['intervals'])
                            if sleeve_helpers:
                                check['sleeve_depth_model']={k:v for k,v in intervals.items() if k!='intervals'}
                    except ValueError as exc:
                        check=dict(status='unmeasured',time=time,reason_code=str(exc))
                    checks.append(check)
                front,ambiguous=held_front(checks,arm,cloth,fallback)
                samples.append(dict(tick=tick,source_tick=source[tick],current_front_slot=front,ambiguous=ambiguous))
                details.append(dict(tick=tick,checks=checks,ambiguous=ambiguous,current_front_slot=front))
            result['pairs'].append(dict(arm_slot=arm,torso_slot=cloth,setup_front_slot=fallback,
                evidence_source='garment_plane_interval_model',samples=samples))
            evidence.append(dict(arm=arm,cloth=cloth,rows=details,pixel_budget_used=64_000_000-probe.remaining))
            if order_probe is not None:
                for key,value in probe.results.items():
                    if key in order_probe.results and order_probe.results[key]!=value:
                        raise ValueError('cloth_constraint_overlap_cache_conflict')
                    order_probe.results[key]=value
    report=dict(profile=PROFILE,authority='none',selected=False,pairs=evidence,hand_mesh_axes=axes,
        unmeasured_samples=sum(c['status']=='unmeasured' for p in evidence for r in p['rows'] for c in r['checks']),
        frame_count=len(ticks),pair_count=len(evidence),pixel_budget_per_pair=64_000_000,
        assumptions=['planar_garment','mesh_hand_axis_to_source_fingertip','same_arm_secondary_influence_envelope'],
        scope='source_frames_and_midpoints_not_continuous_time_or_visual_acceptance')
    report['reused_order_overlap_samples']=len(order_probe.results) if order_probe is not None else 0
    report['bounds_policy']='rendered_triangle_vertices' if order_probe and order_probe.rendered_bounds else 'all_vertices'
    result['ambiguous_pair_samples']=sum(r['ambiguous'] for p in result['pairs'] for r in p['samples'])
    return result,report
