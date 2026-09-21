"""Isolated BVH render partition preserving all triangles and sampled deformation."""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import read_document,canonical_bytes
from autospine_workbench.motion_bundle_reader import VerifiedMotionBundleReader
from autospine_workbench.bvh_parser import parse_bvh
from autospine_workbench.targets.character43.motion_rotation_status import build as verify_source
from autospine_workbench.targets.character43.source_depth_sampler import SegmentDepthSampler
from autospine_workbench.targets.character43.motion_depth_overlap import Probe
from autospine_workbench.targets.character43.torso_depth_refinement import Checker
from autospine_workbench.targets.character43.depth_partition_trace import labels
from autospine_workbench.targets.character43.depth_region_partition import build
from autospine_workbench.targets.character43.depth_partition_compact import compact
from autospine_workbench.targets.character43.affine_pose import sample


def run(job,output,part_limit=128,coalesce=False):
    import re
    if not re.fullmatch(r'motion-[a-f0-9]{32}',job):raise ValueError('job_invalid')
    root=Path('workspace');folder=root/'jobs/motion-intake-v1'/job
    request=read_document(folder/'request.json');result=read_document(folder/'result.json')['result']
    artifact=result['artifact_sha256'];files=AnimatedStore(root).read(artifact)
    address=request['motion_identity'];bundle=VerifiedMotionBundleReader(root).load(address['clip_sha256'],address['bundle_sha256'])
    verify_source(files,artifact,bundle,request)
    if bundle.source_kind=='kimodo_npz':raise ValueError('trace_bvh_required')
    if json.loads(files.get('motion-torso-projection.json',b'{}')).get('applied'):
        raise ValueError('trace_warped_plane_not_supported')
    document=json.loads(files['skeleton.json']);depth=json.loads(files['motion-depth.json'])
    sampler=SegmentDepthSampler(parse_bvh(bundle.raw_bvh),json.loads((bundle.path/'map.json').read_bytes()),
                                request.get('projection',{}).get('yaw_degrees',0))
    probe=Probe(document,files,'external-motion',tiled=True,sparse=True,rendered_bounds=True)
    checker=Checker(probe,sampler,pixelwise=True);traces={};times=set()
    for pair in depth['pairs']:
        arm,body=pair['arm_slot'],pair['torso_slot'];source=pair['samples']
        ticks=[(r['tick'],r['source_tick']) for r in source]
        ticks+= [((a['tick']+b['tick'])/2,(a['source_tick']+b['source_tick'])/2) for a,b in zip(source,source[1:])]
        for tick,source_tick in sorted(ticks):
            time=tick/1e6;times.add(time);counts={}
            def collect(triangle,values):counts.setdefault(triangle,Counter()).update(values)
            try:check=checker.check(arm,body,time,source_tick,on_triangle=collect)
            except ValueError as error:check=dict(status='unmeasured',reason_code=str(error))
            traces.setdefault(arm,[]).append(dict(body=body,time=time,source_tick=source_tick,
                status=check['status'],reason_code=check.get('reason_code'),triangles=counts))
        print(json.dumps(dict(pair=[arm,body],samples=len(ticks))),flush=True)
    selected={};reports={}
    for arm,rows in traces.items():
        mesh=document['skins'][0]['attachments'][arm][probe.slots[arm]['attachment']]
        if coalesce:
            from autospine_workbench.targets.character43.depth_partition_coalesce import coalesced_labels
            selected[arm],reports[arm]=coalesced_labels(len(mesh['triangles'])//3,rows)
        else:selected[arm],reports[arm]=labels(len(mesh['triangles'])//3,rows)
    required=sum(1+sum(a!=b for a,b in zip(values,values[1:])) for values in selected.values())
    output.mkdir(parents=True,exist_ok=True)
    observations_raw=canonical_bytes(traces)
    (output/'observations.json').write_bytes(observations_raw)
    print(json.dumps(dict(required_regions=required,part_limit=part_limit)),flush=True)
    candidate,partition=build(document,sorted(selected),triangle_labels=selected,part_limit=part_limit)
    candidate,partition=compact(candidate,partition)
    for time in sorted(times):
        before=sample(document,'external-motion',time)[0];after=sample(candidate,'external-motion',time)[0]
        for region in partition['regions']:
            expected=[before[region['source_slot']][v] for v in region['source_vertex_indices']]
            if expected!=after[region['slot']]:raise ValueError('trace_deformation_changed')
    payload=canonical_bytes(candidate)
    report=dict(source_job_id=job,source_artifact_sha256=artifact,source_sha256=sha256(bundle.raw_bvh).hexdigest(),
        observations_sha256=sha256(observations_raw).hexdigest(),
        skeleton_sha256=sha256(payload).hexdigest(),partition=partition,traces=reports,
        sampled_frames=len(times),max_vertex_error=0,draw_order_status='unchanged',runtime_status='not_run',
        pixel_budget_used=64_000_000-probe.remaining,authority='none',selected=False)
    output.mkdir(parents=True,exist_ok=True)
    (output/'skeleton.json').write_bytes(payload)
    (output/'report.json').write_bytes(canonical_bytes(report))
    print(json.dumps(dict(regions=len(partition['regions']),frames=len(times),pixel_budget_used=report['pixel_budget_used'])))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('job');parser.add_argument('output',type=Path)
    parser.add_argument('--part-limit',type=int,choices=(128,256,512),default=128)
    parser.add_argument('--coalesce',action='store_true')
    args=parser.parse_args();run(args.job,args.output,args.part_limit,args.coalesce)
