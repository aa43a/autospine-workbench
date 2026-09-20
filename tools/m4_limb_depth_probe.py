"""Inspect arm/leg edges of recorded order cycles without adopting an order."""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import re
from m4_local_depth_probe import analyze
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import read_document,canonical_bytes
from autospine_workbench.motion_bundle_reader import VerifiedMotionBundleReader
from autospine_workbench.bvh_parser import parse_bvh
from autospine_workbench.targets.character43.source_depth_sampler import SegmentDepthSampler
from autospine_workbench.targets.character43.motion_depth_overlap import Probe
from autospine_workbench.targets.character43.mesh_pair_depth import compare,PROFILE
from autospine_workbench.targets.character43.mesh_depth_proxy import vertex_depths
from autospine_workbench.targets.character43.hand_depth_observation import observe
from autospine_workbench.targets.character43.hand_mesh_axis import infer
from autospine_workbench.targets.character43.weighted_depth_interval import build as intervals
from autospine_workbench.targets.spine43.seam_raster import texture
from autospine_workbench.targets.character43.depth_proxy_unknown import inspect as unknown_causes


def run(job,partition,ordering,output,*,leg_intervals=False):
    if not re.fullmatch(r'motion-[a-f0-9]{32}',job): raise ValueError('job_invalid')
    root=Path('workspace'); folder=root/'jobs/motion-intake-v1'/job
    request=read_document(folder/'request.json'); result=read_document(folder/'result.json')
    provenance=analyze(request,result,root,sample_limit=1); digest=result['result']['artifact_sha256']
    region=json.loads((partition/'report.json').read_bytes()); raw=(partition/'skeleton.json').read_bytes()
    order_raw=ordering.read_bytes(); order=json.loads(order_raw)
    if (region['source_artifact_sha256']!=digest or sha256(raw).hexdigest()!=region['skeleton_sha256']
            or order['artifact_sha256']!=digest or order['request_sha256']!=provenance['request_sha256']):
        raise ValueError('limb_probe_source_identity')
    identity=request['motion_identity']
    bundle=VerifiedMotionBundleReader(root).load(identity['clip_sha256'],identity['bundle_sha256'])
    if bundle.source_kind!='bvh': raise ValueError('limb_probe_bvh_only')
    source=SegmentDepthSampler(parse_bvh(bundle.raw_bvh),bundle.bvh_map,request.get('projection',{}).get('yaw_degrees',0))
    doc=json.loads(raw); files=AnimatedStore(root).read(digest); depth=json.loads(files['motion-depth.json'])
    ticks=sorted({r['tick'] for p in depth['pairs'] for r in p['samples']})
    offsets={r['source_tick']-r['tick'] for p in depth['pairs'] for r in p['samples']}
    if len(offsets)!=1: raise ValueError('limb_probe_time_identity')
    offset=offsets.pop(); following=dict(zip(ticks,ticks[1:]))
    arms=set(order['depth_groups']['left']+order['depth_groups']['right'])
    legs={s['name'] for s in doc['slots'] if s['bone'] in ('thigh_l','thigh_r','calf_l','calf_r')}
    probe=Probe(doc,files,'external-motion'); diagnostic=Probe(doc,files,'external-motion'); rows=[]; seen=set()
    if len(order['order']['failures'])>64: raise ValueError('limb_probe_failure_limit')
    def mesh(name): return doc['skins'][0]['attachments'][name][probe.slots[name]['attachment']]
    for failure in order['order']['failures']:
        tick=round(failure['time']*1e6)
        if tick not in ticks: raise ValueError('limb_probe_time_missing')
        for edge in failure.get('conflict',{}).get('edges',[]):
            pair={edge['back'],edge['front']}
            if len(pair&arms)!=1 or len(pair&legs)!=1: continue
            arm=(pair&arms).pop(); leg=(pair&legs).pop()
            for point in [tick]+([(tick+following[tick])/2] if tick in following else []):
                if (arm,leg,point) in seen: continue
                seen.add((arm,leg,point)); time=point/1e6
                try:
                    segments=source(point+offset); hands=observe(source,point+offset,full_hand=True)
                    segments.update(hands['segments']); segments.update(source.leg_segments(point+offset))
                    m=mesh(arm); axis=infer(doc,m,texture(files['images/'+m.get('path',probe.slots[arm]['attachment'])+'.png']))
                    lengths={n:v['length'] for n,v in axis['axes'].items() if n in hands['segments']}
                    a=intervals(doc,m,segments,axis_lengths=lengths)['intervals']
                    b=vertex_depths(doc,mesh(leg),segments,endpoint_caps=True)
                    bounded=intervals(doc,mesh(leg),segments,chain_kind='leg') if leg_intervals else None
                    check=compare(probe,arm,leg,time,a,bounded['intervals'] if bounded else [[v,v] if v is not None else None for v in b])
                    if bounded: check['leg_interval_model']=bounded
                    if check.get('unknown_support',{}).get(leg,0):
                        try: check['leg_unknown_causes']=unknown_causes(diagnostic,leg,arm,time,segments)
                        except ValueError as exc:
                            check['leg_unknown_causes']=dict(status='unmeasured',reason_code=str(exc))
                except ValueError as exc: check=dict(status='unmeasured',reason_code=str(exc))
                rows.append(dict(arm=arm,leg=leg,time=time,source_tick=point+offset,check=check))
    report=dict(profile=PROFILE,authority='none',selected=False,source_artifact_sha256=digest,
        partition_skeleton_sha256=sha256(raw).hexdigest(),ordering_sha256=sha256(order_raw).hexdigest(),
        request_sha256=provenance['request_sha256'],rows=rows,
        assumptions=['segment_axis_planar_cross_sections','quarter_endpoint_caps',
                     'mesh_hand_axis_to_fingertip','same_arm_secondary_influence_envelope']+
                     (['same_leg_secondary_influence_envelope'] if leg_intervals else []),
        scope='recorded_cycle_frames_and_midpoints_not_full_clip_or_order_adoption')
    output.write_bytes(canonical_bytes(report))
    print(json.dumps(dict(samples=len(rows),counts=dict(Counter(r['check']['status'] for r in rows)))))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('job'); parser.add_argument('partition',type=Path)
    parser.add_argument('ordering',type=Path); parser.add_argument('output',type=Path)
    parser.add_argument('--leg-intervals',action='store_true')
    args=parser.parse_args(); run(args.job,args.partition,args.ordering,args.output,leg_intervals=args.leg_intervals)
