"""Run source-pose adaptation through contact/depth checks in an isolated store."""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace

from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes, read_document
from autospine_workbench.automation.motion_target_pose import prepare
from autospine_workbench.automation.motion_target_worker import build_candidate, capture
from autospine_workbench.motion_bundle_reader import VerifiedMotionBundleReader
from autospine_workbench.bvh_parser import parse_bvh


def run(job, output, capture_runtime=False, hip_center=False, yaw=None):
    state=Path('workspace')
    request=read_document(state/'jobs/motion-intake-v1'/job/'request.json')
    if request.get('clip') or request.get('projection') or request.get('torso_projection_profile'):
        raise ValueError('full_pose_experiment_requires_original_view_and_full_clip')
    identity=request['motion_identity']
    bundle=VerifiedMotionBundleReader(state).load(identity['clip_sha256'],identity['bundle_sha256'])
    source=AnimatedStore(state).read(request['character_sha256'])
    kimodo=(bundle.raw_npz,bundle.kimodo_source) if bundle.source_kind=='kimodo_npz' else None
    motion=bundle.motion;view=None
    pose=prepare(bundle,hip_center=hip_center)
    if yaw is not None:
        from autospine_workbench.automation.motion_view_pose import prepare as prepare_view
        motion,view,pose=prepare_view(bundle,yaw)
    output.mkdir(parents=True,exist_ok=False)
    def progress(stage):
        print(json.dumps(dict(stage=stage)),flush=True)
    files,evidence,geometry=build_candidate(source,motion,
        None if kimodo else parse_bvh(bundle.raw_bvh),bundle.kimodo_map if kimodo else bundle.bvh_map,
        character_digest=request['character_sha256'],motion_digest=identity['bundle_sha256'],kimodo=kimodo,
        pose_fit=pose,oblique=view,contact_correction=request.get('contact_correction',True),
        inferred_contact_profile=request.get('inferred_contact_profile'),
        depth_review_profile=request.get('depth_review_profile'),on_stage=progress)
    store=AnimatedStore(output/'isolated-store')
    digest=store.publish(files)
    for name in ('motion-review.json','motion-contact.json','motion-depth.json','deformation.json'):
        if name in files:(output/name).write_bytes(files[name])
    report=dict(job_id=job,source_character_sha256=request['character_sha256'],motion_identity=identity,
        view=view,pose_profile=pose['profile'],
        candidate_bundle_sha256=digest,geometry_passed=geometry['passed'],
        contact_status=evidence['contact_status'],depth_status=evidence['depth_order_status'],
        authority='none',selected=False,production_authorized=False,runtime_status='not_evaluated')
    (output/'report.json').write_bytes(canonical_bytes(report))
    if capture_runtime:
        runtime=capture(SimpleNamespace(workspace_root=Path.cwd().parent),store,digest,output,
            progress=progress,cancel_requested=lambda:False,storage_reference=True)
        report['runtime']=runtime
        report['runtime_status']=runtime['status']
        from autospine_workbench.safe_input_files import read_real_file
        runtime_report=json.loads(read_real_file(output/'runtime/report.json',256*1024*1024,'runtime report'))
        if runtime_report['bundle_sha256']!=digest:
            raise ValueError('full_pose_runtime_identity_mismatch')
        report['runtime_numeric_passed']=runtime_report['passed']
        report['runtime_sampled_frames']=len(runtime_report['results'])
        (output/'report.json').write_bytes(canonical_bytes(report))
    print(json.dumps(report),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('job');parser.add_argument('output',type=Path)
    parser.add_argument('--capture',action='store_true')
    parser.add_argument('--hip-center',action='store_true')
    parser.add_argument('--yaw',type=float)
    args=parser.parse_args();run(args.job,args.output,args.capture,args.hip_center,args.yaw)
