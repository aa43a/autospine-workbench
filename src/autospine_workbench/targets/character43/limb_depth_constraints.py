"""Full-clip arm/leg constraints using explicit weighted depth envelopes."""
from copy import deepcopy
from .cloth_depth_constraints import held_front
from .hand_depth_observation import observe
from .hand_mesh_axis import infer
from .weighted_depth_interval import build as intervals
from .mesh_pair_depth import compare
from .motion_depth_overlap import Probe
from ..spine43.seam_raster import texture

PROFILE='full-clip-arm-leg-depth-envelope-order-v1-experiment'


def build(document,files,animation,depth,sampler,*,order_probe=None):
    if order_probe is not None and (order_probe.document is not document or
            order_probe.files is not files or order_probe.animation!=animation):
        raise ValueError('limb_constraint_probe_identity')
    result=deepcopy(depth); arms=depth['groups']['left']+depth['groups']['right']
    legs=[s['name'] for s in document['slots'] if s['bone'] in ('thigh_l','thigh_r','calf_l','calf_r')]
    if not legs or not arms:
        return result,dict(profile=PROFILE,authority='none',selected=False,status='not_applicable',
            reason_code='no_identified_arm_leg_pairs',pairs=[],frame_count=0,pair_count=0,unmeasured_samples=0,
            scope='no_order_constraint_added_not_anatomical_absence')
    if len(arms)*len(legs)>16: raise ValueError('limb_constraint_pair_limit')
    slots={s['name']:s for s in document['slots']}; index={n:i for i,n in enumerate(slots)}
    source={r['tick']:r['source_tick'] for p in depth['pairs'] for r in p['samples']}
    ticks=sorted(source)
    if not ticks or len(ticks)>512: raise ValueError('limb_constraint_frame_limit')
    offsets={r['source_tick']-r['tick'] for p in depth['pairs'] for r in p['samples']}
    if len(offsets)!=1: raise ValueError('limb_constraint_source_time_mismatch')
    following=dict(zip(ticks,ticks[1:])); evidence=[]; models={}; axes={}
    def mesh(name): return document['skins'][0]['attachments'][name][slots[name]['attachment']]
    for arm in arms:
        m=mesh(arm)
        axes[arm]=infer(document,m,texture(files['images/'+m.get('path',slots[arm]['attachment'])+'.png']))
    for arm in arms:
        for leg in legs:
            probe=Probe(document,files,animation,rendered_bounds=bool(order_probe and order_probe.rendered_bounds),
                        tiled=bool(order_probe and order_probe.tiled),sparse=order_probe.sparse if order_probe else False); rows=[]; samples=[]
            fallback=max((arm,leg),key=index.__getitem__)
            for tick in ticks:
                checks=[]
                for point in [tick]+([(tick+following[tick])/2] if tick in following else []):
                    time=point/1e6; source_tick=source[tick]+point-tick
                    try:
                        pair=probe.pair(arm,leg,time)
                        if not pair['overlap_pixels']: check=dict(status='no_overlap',time=time)
                        else:
                            if point not in models:
                                segments=sampler(source_tick); hands=observe(sampler,source_tick,full_hand=True)
                                segments.update(hands['segments']); segments.update(sampler.leg_segments(source_tick))
                                models[point]=(segments,hands)
                            segments,hands=models[point]
                            lengths={n:v['length'] for n,v in axes[arm]['axes'].items() if n in hands['segments']}
                            a=intervals(document,mesh(arm),segments,axis_lengths=lengths)
                            b=intervals(document,mesh(leg),segments,chain_kind='leg')
                            check=compare(probe,arm,leg,time,a['intervals'],b['intervals'])
                    except ValueError as exc: check=dict(status='unmeasured',time=time,reason_code=str(exc))
                    checks.append(check)
                front,ambiguous=held_front(checks,arm,leg,fallback)
                samples.append(dict(tick=tick,source_tick=source[tick],current_front_slot=front,ambiguous=ambiguous))
                rows.append(dict(tick=tick,checks=checks,current_front_slot=front,ambiguous=ambiguous))
            result['pairs'].append(dict(arm_slot=arm,torso_slot=leg,setup_front_slot=fallback,
                evidence_source='arm_leg_depth_envelope_model',samples=samples))
            evidence.append(dict(arm=arm,leg=leg,rows=rows,pixel_budget_used=64_000_000-probe.remaining))
            if order_probe is not None:
                for key,value in probe.results.items():
                    if key in order_probe.results and order_probe.results[key]!=value:
                        raise ValueError('limb_constraint_overlap_cache_conflict')
                    order_probe.results[key]=value
    result['ambiguous_pair_samples']=sum(r['ambiguous'] for p in result['pairs'] for r in p['samples'])
    report=dict(profile=PROFILE,authority='none',selected=False,pairs=evidence,hand_mesh_axes=axes,
        frame_count=len(ticks),pair_count=len(evidence),pixel_budget_per_pair=64_000_000,
        unmeasured_samples=sum(c['status']=='unmeasured' for p in evidence for r in p['rows'] for c in r['checks']),
        assumptions=['segment_axis_planar_cross_sections','quarter_endpoint_caps','mesh_hand_axis_to_source_fingertip',
                     'same_arm_secondary_influence_envelope','same_leg_secondary_influence_envelope'],
        scope='source_frames_and_midpoints_not_continuous_time_or_visual_acceptance')
    report['bounds_policy']='rendered_triangle_vertices' if order_probe and order_probe.rendered_bounds else 'all_vertices'
    return result,report
