"""Inspect explicit sleeve helper planes over an exact motion and its midpoints."""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import re

from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import read_document,canonical_bytes
from autospine_workbench.motion_bundle_reader import VerifiedMotionBundleReader
from autospine_workbench.targets.character43.motion_rotation_status import build as verify_source
from autospine_workbench.targets.character43.sleeve_depth_plane import at,PROFILE
from m4_regional_replay_inputs import prepare


def run(job,helpers,output):
    if not re.fullmatch(r'motion-[a-f0-9]{32}',job):raise ValueError('invalid_motion_job')
    if output.exists():raise ValueError('sleeve_plane_output_exists')
    if not helpers or len(helpers)>8:raise ValueError('sleeve_plane_helper_limit')
    root=Path('workspace');folder=root/'jobs/motion-intake-v1'/job
    request=read_document(folder/'request.json');result=read_document(folder/'result.json')['result']
    identity=request['motion_identity'];store=AnimatedStore(root)
    files=store.read(result['artifact_sha256'])
    bundle=VerifiedMotionBundleReader(root).load(identity['clip_sha256'],identity['bundle_sha256'])
    verify_source(files,result['artifact_sha256'],bundle,request)
    files,receipt=prepare(files,store.read(request['character_sha256']),request['character_sha256'])
    if json.loads(files.get('motion-torso-projection.json',b'{}')).get('applied'):
        raise ValueError('sleeve_plane_warped_candidate_unsupported')
    yaw=request.get('projection',{}).get('yaw_degrees',0)
    if bundle.source_kind=='kimodo_npz':
        from autospine_workbench.targets.character43.kimodo_depth_sampler import KimodoDepthSampler
        sampler=KimodoDepthSampler(bundle.raw_npz,bundle.kimodo_source,bundle.kimodo_map,yaw,
                                  interpolation='linear_observed_positions')
    else:
        from autospine_workbench.bvh_parser import parse_bvh
        from autospine_workbench.targets.character43.source_depth_sampler import SegmentDepthSampler
        sampler=SegmentDepthSampler(parse_bvh(bundle.raw_bvh),bundle.bvh_map,yaw)
    depth=json.loads(files['motion-depth.json']);ticks={}
    for pair in depth['pairs']:
        for row in pair['samples']:
            if row['tick'] in ticks and ticks[row['tick']]!=row['source_tick']:
                raise ValueError('sleeve_plane_source_time_conflict')
            ticks[row['tick']]=row['source_tick']
    if not 1<len(ticks)<=512:raise ValueError('sleeve_plane_frame_limit')
    times=dict(ticks);ordered=sorted(ticks)
    for a,b in zip(ordered,ordered[1:]):
        if ticks[b]-ticks[a]!=b-a:raise ValueError('sleeve_plane_source_time_scale')
        times[(a+b)/2]=(ticks[a]+ticks[b])/2
    document=json.loads(files['skeleton.json']);rows=[]
    for helper,parent in sorted(helpers.items()):
        samples=[]
        for tick,source_tick in sorted(times.items()):
            try:
                model=at(document,'external-motion',tick/1e6,sampler,source_tick,helper,parent)
                samples.append(dict(time=tick/1e6,status='candidate_plane',model=model))
            except ValueError as exc:
                samples.append(dict(time=tick/1e6,status='unavailable',reason_code=str(exc)))
        rows.append(dict(helper=helper,parent=parent,samples=samples,
            counts=dict(Counter(s['status'] for s in samples)),
            reasons=dict(Counter(s['reason_code'] for s in samples if s['status']=='unavailable'))))
    report=dict(profile=PROFILE,source_job=job,source_artifact_sha256=result['artifact_sha256'],
        request_sha256=sha256((folder/'request.json').read_bytes()).hexdigest(),motion_identity=identity,
        replay_inputs=receipt,rows=rows,authority='none',selected=False,runtime='not_captured',
        scope='plane_conditioning_only_not_cloth_depth_accuracy_or_sorting_acceptance')
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('xb') as handle:handle.write(canonical_bytes(report))
    print(json.dumps([dict(helper=r['helper'],counts=r['counts'],reasons=r['reasons']) for r in rows]))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('job');parser.add_argument('output',type=Path)
    parser.add_argument('--helper',action='append',required=True,help='Explicit helper=forearm_l/r binding')
    args=parser.parse_args();pairs=[v.split('=') for v in args.helper]
    if any(len(v)!=2 for v in pairs) or len({v[0] for v in pairs})!=len(pairs):
        parser.error('each helper must occur once with one parent')
    run(args.job,dict(pairs),args.output)
