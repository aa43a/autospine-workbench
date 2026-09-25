"""One bounded order-refinement trial in the already baked torso coordinate frame."""
import argparse
from collections import Counter
import json
from pathlib import Path

from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.bvh_parser import parse_bvh
from autospine_workbench.motion_bundle_reader import VerifiedMotionBundleReader
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.targets.character43.motion_rotation_status import build as verify_source
from autospine_workbench.targets.character43.torso_projection_profile import prepare
from autospine_workbench.targets.character43.torso_baked_depth_plane import BakedWarpPlane
from autospine_workbench.targets.character43.source_depth_sampler import SegmentDepthSampler
from autospine_workbench.targets.character43.kimodo_depth_sampler import KimodoDepthSampler
from autospine_workbench.targets.character43.motion_depth_overlap import Probe
from autospine_workbench.targets.character43.depth_straddle_refine import refine
from autospine_workbench.targets.character43.motion_depth_order import build as order


def run(state,job,output):
    if output.exists():raise ValueError('output_exists')
    folder=state/'jobs/motion-intake-v1'/job
    request=json.loads((folder/'request.json').read_bytes())
    result=json.loads((folder/'result.json').read_bytes())
    if result['status']!='succeeded':raise ValueError('source_job_incomplete')
    artifact=result['result']['artifact_sha256'];files=AnimatedStore(state).read(artifact)
    identity=request['motion_identity']
    bundle=VerifiedMotionBundleReader(state).load(identity['clip_sha256'],identity['bundle_sha256'])
    verify_source(files,artifact,bundle,request)
    document=json.loads(files['skeleton.json']);depth=json.loads(files['motion-depth.json'])
    receipt=json.loads(files['motion-torso-projection.json'])
    if not receipt['applied']:raise ValueError('torso_not_applied')
    provider=BakedWarpPlane(document,'external-motion',receipt,prepare(bundle,request))
    yaw=request['projection']['yaw_degrees']
    sampler=(KimodoDepthSampler(bundle.raw_npz,bundle.kimodo_source,bundle.kimodo_map,yaw,
        interpolation='linear_observed_positions') if bundle.source_kind=='kimodo_npz'
        else SegmentDepthSampler(parse_bvh(bundle.raw_bvh),bundle.bvh_map,yaw))
    probe=Probe(document,files,'external-motion',rendered_bounds=True,tiled=True,sparse=True)
    refined,evidence=refine(document,files,'external-motion',depth,sampler,torso_plane=True,
        rendered_bounds=True,order_probe=probe,tiled=True,sparse=True,pair_budgets=True,
        plane_provider=provider)
    candidate,ordering=order(document,'external-motion',refined,probe)
    report=dict(profile='baked-torso-order-refinement-probe-v1',artifact_sha256=artifact,
        request_sha256=canonical_sha256(request),source_identity=identity,
        original_failure_count=len(depth.get('order',{}).get('failures',[])),
        refinement=evidence,order=ordering,candidate_available=candidate is not None,
        authority='none',selected=False,production_authorized=False,
        scope='source_frames_and_midpoints_proxy_order_not_surface_truth_or_visual_acceptance')
    output.mkdir(parents=True)
    (output/'report.json').write_bytes(canonical_bytes(report))
    if candidate is not None:(output/'candidate.skeleton.json').write_bytes(canonical_bytes(candidate))
    print(json.dumps(dict(candidate_available=candidate is not None,
        resolved=evidence['resolved_rows'],remaining=evidence['remaining_rows'],
        failures=dict(Counter(r['reason_code'] for r in ordering['failures'])))),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('job');p.add_argument('output',type=Path);p.add_argument('--state',type=Path,default=Path('workspace'))
    a=p.parse_args()
    if not __import__('re').fullmatch('motion-[a-f0-9]{32}',a.job):raise ValueError('invalid_job')
    run(a.state,a.job,a.output)
