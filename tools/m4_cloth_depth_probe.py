"""Test explicit torso-plane garment depth at exact regional cycle samples."""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import re

from m4_local_depth_probe import analyze
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import read_document, canonical_bytes
from autospine_workbench.motion_bundle_reader import VerifiedMotionBundleReader
from autospine_workbench.bvh_parser import parse_bvh
from autospine_workbench.targets.character43.source_depth_sampler import SegmentDepthSampler
from autospine_workbench.targets.character43.cloth_depth_plane import at, PROFILE
from autospine_workbench.targets.character43.motion_depth_overlap import Probe
from autospine_workbench.targets.character43.mesh_depth_proxy import overlap_support
from autospine_workbench.targets.character43.hand_depth_observation import observe
from autospine_workbench.targets.character43.depth_proxy_unknown import inspect as unknown_causes
from autospine_workbench.targets.character43.hand_mesh_axis import infer
from autospine_workbench.targets.spine43.seam_raster import texture
from autospine_workbench.targets.character43.weighted_depth_interval import build as interval_build


def run(job, partition, ordering, output, *, hand_depth=False, diagnose_unknown=False, mesh_axis=False, interval_influences=False):
    if not re.fullmatch(r'motion-[a-f0-9]{32}',job): raise ValueError('job_invalid')
    root=Path('workspace'); folder=root/'jobs/motion-intake-v1'/job
    request=read_document(folder/'request.json'); result=read_document(folder/'result.json')
    provenance=analyze(request,result,root,sample_limit=1)
    region=json.loads((partition/'report.json').read_bytes()); raw=(partition/'skeleton.json').read_bytes()
    order_raw=ordering.read_bytes(); order=json.loads(order_raw)
    digest=result['result']['artifact_sha256']
    if (region['source_artifact_sha256']!=digest or sha256(raw).hexdigest()!=region['skeleton_sha256']
            or order['artifact_sha256']!=digest or order['request_sha256']!=provenance['request_sha256']):
        raise ValueError('cloth_probe_source_identity')
    identity=request['motion_identity']
    bundle=VerifiedMotionBundleReader(root).load(identity['clip_sha256'],identity['bundle_sha256'])
    if bundle.source_kind!='bvh': raise ValueError('cloth_probe_bvh_only')
    sampler=SegmentDepthSampler(parse_bvh(bundle.raw_bvh),bundle.bvh_map,request.get('projection',{}).get('yaw_degrees',0))
    document=json.loads(raw); files=AnimatedStore(root).read(digest)
    depth=json.loads(files['motion-depth.json'])
    ticks=sorted({r['tick'] for p in depth['pairs'] for r in p['samples']})
    offsets={r['source_tick']-r['tick'] for p in depth['pairs'] for r in p['samples']}
    if len(offsets)!=1: raise ValueError('cloth_probe_source_time_identity')
    offset=offsets.pop(); next_tick=dict(zip(ticks,ticks[1:]))
    probe=Probe(document,files,'external-motion')
    diagnostic=Probe(document,files,'external-motion') if diagnose_unknown else None
    regions={r['slot'] for r in region['regions'] if r['group']=='mixed'}
    arms=set(order['depth_groups']['left']+order['depth_groups']['right']); rows=[]
    axes={}
    if mesh_axis:
        for arm in arms:
            slot=probe.slots[arm]; mesh=document['skins'][0]['attachments'][arm][slot['attachment']]
            axes[arm]=infer(document,mesh,texture(files['images/'+mesh.get('path',slot['attachment'])+'.png']))
    failures=order['order']['failures']
    if len(failures)>64: raise ValueError('cloth_probe_failure_limit')
    for failure in failures:
        tick=round(failure['time']*1e6)
        if tick not in ticks: raise ValueError('cloth_probe_time_missing')
        times=[tick]+([(tick+next_tick[tick])/2] if tick in next_tick else [])
        for edge in failure.get('conflict',{}).get('edges',[]):
            pair={edge['back'],edge['front']}
            if len(pair & arms)!=1 or len(pair & regions)!=1: continue
            arm=(pair & arms).pop(); cloth=(pair & regions).pop()
            for target_tick in times:
                source_tick=target_tick+offset; time=target_tick/1e6
                try:
                    plane=at(document,'external-motion',time,sampler,source_tick)
                    segments=sampler(source_tick)
                    hands=observe(sampler,source_tick,full_hand=mesh_axis) if hand_depth or mesh_axis else None
                    if hands: segments.update(hands['segments'])
                    lengths={n:v['length'] for n,v in axes.get(arm,{}).get('axes',{}).items()
                             if hands and n in hands['segments']}
                    interval=None
                    if interval_influences:
                        mesh=document['skins'][0]['attachments'][arm][probe.slots[arm]['attachment']]
                        interval=interval_build(document,mesh,segments,axis_lengths=lengths)
                    check=overlap_support(probe,arm,cloth,time,segments,
                                          endpoint_caps=True,reference_plane=plane['coefficients'],axis_lengths=lengths,
                                          depth_intervals=interval['intervals'] if interval else None)
                    row=dict(time=time,source_tick=source_tick,plane=plane,hand_depth=hands,check=check)
                    if interval: row['depth_interval_model']=interval
                    if diagnostic is not None:
                        try: row['unknown_causes']=unknown_causes(diagnostic,arm,cloth,time,segments,axis_lengths=lengths)
                        except ValueError as exc:
                            row['unknown_causes']=dict(status='unmeasured',reason_code=str(exc))
                        if interval: row['pre_interval_unknown_causes']=row.pop('unknown_causes')
                except ValueError as exc:
                    row=dict(time=time,source_tick=source_tick,check=dict(status='unmeasured',reason_code=str(exc)))
                rows.append(dict(arm=arm,cloth=cloth,**row))
    report=dict(profile=PROFILE,authority='none',selected=False,source_artifact_sha256=digest,
                partition_skeleton_sha256=region['skeleton_sha256'],ordering_sha256=sha256(order_raw).hexdigest(),
                request_sha256=provenance['request_sha256'],rows=rows,
                hand_mesh_axes=axes,
                scope='recorded_cycle_frames_and_midpoints_not_full_clip_or_order_adoption')
    output.write_bytes(canonical_bytes(report))
    print(json.dumps(dict(samples=len(rows),counts=dict(Counter(r['check']['status'] for r in rows)))))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('job'); parser.add_argument('partition',type=Path)
    parser.add_argument('ordering',type=Path); parser.add_argument('output',type=Path)
    parser.add_argument('--hand-depth',action='store_true')
    parser.add_argument('--diagnose-unknown',action='store_true')
    parser.add_argument('--mesh-hand-axis',action='store_true')
    parser.add_argument('--interval-influences',action='store_true')
    args=parser.parse_args(); run(args.job,args.partition,args.ordering,args.output,
                                hand_depth=args.hand_depth,diagnose_unknown=args.diagnose_unknown,mesh_axis=args.mesh_hand_axis,
                                interval_influences=args.interval_influences)
