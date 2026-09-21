"""Recheck an isolated torso bake without reusing the original target QA result."""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path

from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes,read_document
from autospine_workbench.motion_bundle_reader import VerifiedMotionBundleReader
from autospine_workbench.bvh_parser import parse_bvh
from autospine_workbench.bvh_fk import bvh_frame_ticks
from autospine_workbench.kimodo_npz_projection import kimodo_frame_ticks
from autospine_workbench.targets.character43.motion_clip import boundaries
from autospine_workbench.targets.character43.numeric_reference import read as read_reference
from autospine_workbench.targets.character43.torso_projection_validation import contact_preservation,depth_check


def run(root):
    receipt=json.loads((root/'report.json').read_bytes())
    request=read_document(Path('workspace/jobs/motion-intake-v1')/receipt['job_id']/'request.json')
    if request['motion_identity']!=receipt['motion_identity']:raise ValueError('torso_validation_source_changed')
    original=AnimatedStore(Path('workspace')).read(receipt['source_artifact_sha256'])
    files=AnimatedStore(root/'isolated-store').read(receipt['candidate_bundle_sha256'])
    if (sha256(original['skeleton.json']).hexdigest()!=receipt['source_skeleton_sha256'] or
        sha256(files['skeleton.json']).hexdigest()!=receipt['skeleton_sha256']):
        raise ValueError('torso_validation_skeleton_changed')
    identity=request['motion_identity']
    bundle=VerifiedMotionBundleReader(Path('workspace')).load(identity['clip_sha256'],identity['bundle_sha256'])
    document=json.loads(files['skeleton.json']);animation='external-motion'
    times=[r['time'] for r in read_reference(files)['animations'][animation]]
    contact=contact_preservation(json.loads(original['skeleton.json']),document,animation,times)
    contact['original_contact_status']=json.loads(original['motion-contact.json'])['status']
    (root/'contact-preservation.json').write_bytes(canonical_bytes(contact))
    print(json.dumps(dict(contact=contact['status'],frames=len(times))),flush=True)
    kimodo=(bundle.raw_npz,bundle.kimodo_source) if bundle.source_kind=='kimodo_npz' else None
    bvh=None if kimodo else parse_bvh(bundle.raw_bvh)
    ticks=kimodo_frame_ticks(bundle.kimodo_source) if kimodo else bvh_frame_ticks(bvh)
    depth=depth_check(document,files,animation,bvh,bundle.kimodo_map if kimodo else bundle.bvh_map,
        kimodo=kimodo,clip_bounds=boundaries(request.get('clip'),ticks),
        yaw_degrees=request.get('projection',{}).get('yaw_degrees'))
    (root/'depth-recheck.json').write_bytes(canonical_bytes(depth))
    report=dict(profile='torso-candidate-validation-v1',authority='none',selected=False,
        candidate_bundle_sha256=receipt['candidate_bundle_sha256'],skeleton_sha256=receipt['skeleton_sha256'],
        contact=contact,depth_overlap=depth['target_overlap'],
        depth_failures=dict(Counter(r['reason_code'] for r in depth['order']['failures'])),
        order_candidate_available=depth['order_candidate_available'],
        local_depth_status='not_evaluated_visual_bake_has_original_bone_guides',
        production_authorized=False)
    (root/'validation.json').write_bytes(canonical_bytes(report))
    print(json.dumps(dict(depth_failures=report['depth_failures'],overlap=report['depth_overlap'])),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('root',type=Path)
    run(parser.parse_args().root)
