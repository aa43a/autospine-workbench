"""Fresh source/overlap diagnostics for an isolated calibrated walking capture."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.motion_bundle_reader import VerifiedMotionBundleReader
from autospine_workbench.bvh_parser import parse_bvh
from autospine_workbench.targets.character43.motion_depth import build
from autospine_workbench.targets.character43.motion_depth_overlap import inspect
from autospine_workbench.targets.character43.motion_depth_order import build as order
from autospine_workbench.resolved_project import canonical_sha256


def run(state, parent, capture):
    read=lambda p:json.loads(p.read_bytes())
    request=read(parent/'request.json');prior=read(parent/'report.json')
    receipt=read(capture/'report.json');runtime=read(capture/'runtime/report.json')
    if (receipt['parent_artifact']!=prior['candidate_bundle_sha256']
            or canonical_sha256(request)!=prior['request_sha256']
            or runtime['bundle_sha256']!=receipt['candidate_bundle_sha256']
            or runtime.get('passed') is not True or request.get('clip')):
        raise ValueError('walking_depth_capture_identity')
    files=AnimatedStore(capture/'isolated-store').read(receipt['candidate_bundle_sha256'])
    previous=AnimatedStore(parent/'isolated-store').read(receipt['parent_artifact'])
    if files['motion-ir.json']!=previous['motion-ir.json']:
        raise ValueError('walking_depth_motion_changed')
    identity=request['motion_identity']
    observation=json.loads(previous['motion-moving-ankles.json'])['source_observation']
    if (observation['source_bundle_sha256']!=identity['bundle_sha256']
            or observation['motion_sha256']!=identity['clip_sha256']):
        raise ValueError('walking_depth_source_changed')
    bundle=VerifiedMotionBundleReader(state).load(identity['clip_sha256'],identity['bundle_sha256'])
    if bundle.source_kind!='bvh':raise ValueError('walking_depth_requires_bvh')
    doc=json.loads(files['skeleton.json'])
    options=request.get('projection') or {}
    depth=build(doc,parse_bvh(bundle.raw_bvh),bundle.bvh_map,
                **({'yaw_degrees':options['yaw_degrees']} if 'yaw_degrees' in options else {}))
    depth,probe=inspect(doc,files,'external-motion',depth)
    _,proposal=order(doc,'external-motion',depth,probe)
    report=dict(candidate_bundle_sha256=receipt['candidate_bundle_sha256'],
        skeleton_sha256=sha256(files['skeleton.json']).hexdigest(),source_identity=identity,
        depth=depth,order=proposal,authority='none',selected=False,
        scope='source_depth_and_cpu_overlap_no_order_change_or_visual_acceptance')
    with (capture/'depth-review.json').open('xb') as stream:stream.write(canonical_bytes(report))
    print(json.dumps(dict(status=proposal['status'],failures=len(proposal['failures']),
        overlap=depth['target_overlap'])),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('state','parent','capture'):p.add_argument(key,type=Path)
    a=p.parse_args();run(a.state,a.parent,a.capture)
