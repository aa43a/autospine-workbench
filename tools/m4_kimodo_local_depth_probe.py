"""Local depth on exact Kimodo source frames; no ordering or midpoint adoption."""
import argparse
from collections import Counter
import json
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import read_document
from autospine_workbench.motion_bundle_reader import VerifiedMotionBundleReader
from autospine_workbench.targets.character43.motion_rotation_status import build as verify_source
from autospine_workbench.targets.character43.kimodo_depth_sampler import KimodoDepthSampler
from autospine_workbench.targets.character43.motion_depth_overlap import Probe
from autospine_workbench.targets.character43.torso_depth_refinement import Checker
from autospine_workbench.targets.character43.torso_warp_depth_plane import WarpedPlane
from autospine_workbench.targets.character43.torso_projection_profile import prepare
from m4_motion_cohort import api


def run(job,output):
    task=api('http://127.0.0.1:8918','/api/motions/'+job)
    if task['status']!='succeeded' or task.get('kind')!='adapt':raise ValueError('completed_target_required')
    request=read_document(Path('workspace/jobs/motion-intake-v1')/job/'request.json')
    artifact=task['result']['artifact_sha256'];files=AnimatedStore(Path('workspace')).read(artifact)
    receipt=json.loads(files.get('motion-torso-projection.json',b'{}'))
    identity=request['motion_identity']
    bundle=VerifiedMotionBundleReader(Path('workspace')).load(identity['clip_sha256'],identity['bundle_sha256'])
    if bundle.source_kind!='kimodo_npz':raise ValueError('kimodo_source_required')
    verify_source(files,artifact,bundle,request)
    mapping=json.loads((bundle.path/'map.json').read_bytes())
    sampler=KimodoDepthSampler(bundle.raw_npz,bundle.kimodo_source,mapping,
                              request.get('projection',{}).get('yaw_degrees',0))
    document=json.loads(files['skeleton.json']);depth=json.loads(files['motion-depth.json'])
    probe=Probe(document,files,'external-motion',tiled=True,sparse=True,rendered_bounds=True)
    options={'plane_provider':WarpedPlane(receipt,prepare(bundle,request))} if receipt.get('applied') else {}
    checker=Checker(probe,sampler,**options);rows=[]
    for pair in depth['pairs']:
        for sample in pair['samples']:
            time=sample['tick']/1e6
            try:check=checker.check(pair['arm_slot'],pair['torso_slot'],time,sample['source_tick'])
            except ValueError as error:check=dict(status='unmeasured',reason_code=str(error),time=time)
            rows.append(dict(pair=[pair['arm_slot'],pair['torso_slot']],source_tick=sample['source_tick'],check=check))
        print(json.dumps(dict(pair=[pair['arm_slot'],pair['torso_slot']],remaining=probe.remaining)),flush=True)
    result=dict(profile='soma77-local-depth-source-frame-probe-v1',job_id=job,artifact_sha256=artifact,
        source_identity=sampler.identity,interpolation=sampler.interpolation,
        torso_anchor_mode='compensated_source_key_origins' if options else 'original_bone_origins',
        counts=dict(Counter(r['check']['status'] for r in rows)),records=rows,
        hand_mesh_axes=checker.axes,pixel_budget_used=64_000_000-probe.remaining,
        scope='source_frame_model_only_not_midpoints_cloth_depth_order_or_runtime_acceptance',
        authority='none',selected=False,production_authorized=False)
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('records','hand_mesh_axes')}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('job');parser.add_argument('output',type=Path)
    args=parser.parse_args();run(args.job,args.output)
