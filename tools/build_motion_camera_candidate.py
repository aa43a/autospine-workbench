"""Build an isolated full-camera candidate through target QA and official capture."""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace
from urllib.request import urlopen
from autospine_workbench.motion_bundle_reader import VerifiedMotionBundleReader
from autospine_workbench.bvh_parser import parse_bvh
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.motion_camera_pose import prepare
from autospine_workbench.automation.motion_target_worker import build_candidate
from autospine_workbench.automation.character_capture import capture
from autospine_workbench.targets.character43.camera_ankle_targets import extract
from autospine_workbench.targets.character43.motion_readiness import build as readiness
from autospine_workbench.targets.character43.phase_contact_policy import PROFILE as CONTACT
from autospine_workbench.targets.character43.motion_depth_overlap import SPARSE_DEPTH_PROFILE


def main():
    p=argparse.ArgumentParser();p.add_argument('--state',type=Path,required=True)
    p.add_argument('--workspace',type=Path,required=True);p.add_argument('--source',required=True)
    p.add_argument('--character',required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--end-yaw',type=float,default=360);args=p.parse_args()
    job=json.loads(urlopen('http://127.0.0.1:8918/api/motions/'+args.source,timeout=30).read())
    identity=job['result']['motion'];store=AnimatedStore(args.state)
    bundle=VerifiedMotionBundleReader(args.state).load(identity['clip_sha256'],identity['bundle_sha256'])
    duration=bundle.motion['duration_ticks']/bundle.motion['ticks_per_second']
    keys=[dict(time=0,yaw=0),dict(time=duration,yaw=args.end_yaw)]
    motion,receipt,pose=prepare(bundle,keys);ankles=extract(bundle,keys)
    args.output.mkdir(parents=True,exist_ok=False)
    save=lambda name,value:(args.output/name).write_text(json.dumps(value,indent=2,allow_nan=False),encoding='utf-8')
    save('request.json',dict(source_job=args.source,source=identity,character=args.character,keys=keys))
    kimodo=(bundle.raw_npz,bundle.kimodo_source) if bundle.source_kind=='kimodo_npz' else None
    progress=lambda stage:print(json.dumps(dict(stage=stage)),flush=True)
    files,evidence,geometry=build_candidate(store.read(args.character),motion,None if kimodo else parse_bvh(bundle.raw_bvh),
        bundle.kimodo_map if kimodo else bundle.bvh_map,kimodo=kimodo,character_digest=args.character,
        motion_digest=bundle.bundle_sha256,contact_correction=False,inferred_contact_profile=CONTACT,
        depth_review_profile=SPARSE_DEPTH_PROFILE,on_stage=progress,oblique=receipt,pose_fit=pose,moving_ankles=ankles)
    digest=store.publish(files);save('candidate.json',dict(artifact_sha256=digest,evidence=evidence,geometry=geometry))
    runtime=capture(SimpleNamespace(workspace_root=args.workspace),store,digest,args.output,
        progress=progress,cancel_requested=lambda:False,storage_reference=True)
    save('capture.json',runtime)
    report=json.loads((args.output/'runtime/report.json').read_bytes()) if 'report.json' in runtime.get('files',{}) else None
    status=readiness(files,digest,report);save('readiness.json',status)
    print(json.dumps(dict(artifact=digest,geometry_passed=geometry['passed'],readiness=status['status'],
        stages=[dict(stage=r['stage'],status=r['status']) for r in status['stages']])),flush=True)


if __name__=='__main__':main()
