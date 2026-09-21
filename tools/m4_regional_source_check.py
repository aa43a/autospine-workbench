"""Replay regional depth on an exact existing candidate without replacing it."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import read_document, canonical_bytes
from autospine_workbench.motion_bundle_reader import VerifiedMotionBundleReader
from autospine_workbench.bvh_parser import parse_bvh
from autospine_workbench.targets.character43.motion_rotation_status import build as verify_source
from autospine_workbench.targets.character43.regional_depth_profile import apply


def run(job, output, *, sparse=False):
    if not re.fullmatch(r'motion-[a-f0-9]{32}', job):
        raise ValueError('invalid_motion_job')
    if output.exists():
        raise ValueError('regional_check_output_exists')
    root = Path('workspace'); folder = root/'jobs/motion-intake-v1'/job
    request = read_document(folder/'request.json')
    result = read_document(folder/'result.json')['result']; identity = request['motion_identity']
    bundle = VerifiedMotionBundleReader(root).load(identity['clip_sha256'],identity['bundle_sha256'])
    files = AnimatedStore(root).read(result['artifact_sha256'])
    verify_source(files,result['artifact_sha256'],bundle,request)
    if json.loads(files.get('motion-torso-projection.json',b'{}')).get('applied'):
        raise ValueError('regional_check_warped_plane_unsupported')
    kimodo = (bundle.raw_npz,bundle.kimodo_source) if bundle.source_kind == 'kimodo_npz' else None
    document, depth, transform = apply(json.loads(files['skeleton.json']),files,'external-motion',
        json.loads(files['motion-depth.json']),None if kimodo else parse_bvh(bundle.raw_bvh),
        bundle.kimodo_map if kimodo else bundle.bvh_map,kimodo=kimodo,
        yaw=request.get('projection',{}).get('yaw_degrees',0),sparse=sparse,
        on_stage=lambda stage: print(stage,flush=True))
    output.mkdir(parents=True)
    report = dict(source_job=job,source_artifact_sha256=result['artifact_sha256'],
        request_sha256=sha256((folder/'request.json').read_bytes()).hexdigest(),
        motion_identity=identity,depth=depth,transform=transform,authority='none',selected=False,
        runtime='not_captured',scope='regional_source_replay_not_visual_acceptance')
    (output/'report.json').write_bytes(canonical_bytes(report))
    if transform:
        (output/'skeleton.json').write_bytes(canonical_bytes(document))
    print(json.dumps(dict(selected=depth['selected'],unmeasured=depth['regional']['unmeasured_samples'],
                         failures=len(depth['order']['failures']))),flush=True)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('job'); parser.add_argument('output',type=Path)
    policy=parser.add_mutually_exclusive_group()
    policy.add_argument('--sparse',action='store_true')
    policy.add_argument('--tight-sparse',action='store_true')
    policy.add_argument('--tight-depth-groups',action='store_true')
    args=parser.parse_args();run(args.job,args.output,
        sparse='tight_depth_groups' if args.tight_depth_groups else
               'tight_triangle_boxes' if args.tight_sparse else args.sparse)
