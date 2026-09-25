"""Run the workbench candidate builder offline against exact persisted sources."""
import argparse
import json
from pathlib import Path

from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.motion_ankle_policy import PROFILE, prepare as ankles
from autospine_workbench.automation.motion_pose_policy import prepare_inputs
from autospine_workbench.automation.motion_target_worker import build_candidate
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.bvh_parser import parse_bvh
from autospine_workbench.motion_bundle_reader import VerifiedMotionBundleReader
from autospine_workbench.resolved_project import canonical_sha256


def run(state, source_request, output, source_pose=False, shared_yaw=None, reference_torso=False):
    parent = json.loads(source_request.read_bytes())
    request = dict(parent, moving_ankle_profile=PROFILE, contact_correction=False)
    if source_pose:
        from autospine_workbench.automation.motion_target_pose import HIP_PROFILE
        request['pose_profile'] = HIP_PROFILE
    if shared_yaw is not None:
        from autospine_workbench.automation.motion_view_pose import PROFILE as VIEW_PROFILE
        request.update(pose_profile=VIEW_PROFILE,projection=dict(
            profile='constant-yaw-source-motion-v1',yaw_degrees=shared_yaw))
        request.pop('projection_selection',None)
    if reference_torso:
        from autospine_workbench.targets.character43.torso_projection_profile import REFERENCE_PROFILE
        request.update(torso_projection_profile=REFERENCE_PROFILE,
                       depth_review_profile='external-arm-torso-depth-overlap-v2')
    from autospine_workbench.automation.motion_torso_policy import select as select_torso
    torso_profile=select_torso(request,request.get('depth_review_profile'))
    identity = request['motion_identity']
    bundle = VerifiedMotionBundleReader(state).load(identity['clip_sha256'], identity['bundle_sha256'])
    motion, view, fitted = prepare_inputs(bundle, request)
    observation = ankles(bundle, request)
    torso=None
    if torso_profile:
        from autospine_workbench.targets.character43.torso_projection_profile import prepare
        torso=prepare(bundle,request)
    if request.get('clip'):
        raise ValueError('probe_requires_unclipped_request')
    output.mkdir(parents=True, exist_ok=False)
    (output/'request.json').write_bytes(canonical_bytes(request))
    kimodo = (bundle.raw_npz, bundle.kimodo_source) if bundle.source_kind == 'kimodo_npz' else None
    files, evidence, geometry = build_candidate(AnimatedStore(state).read(request['character_sha256']),
        motion, None if kimodo else parse_bvh(bundle.raw_bvh), bundle.kimodo_map if kimodo else bundle.bvh_map,
        kimodo=kimodo, character_digest=request['character_sha256'], motion_digest=bundle.bundle_sha256,
        contact_correction=False, inferred_contact_profile=request.get('inferred_contact_profile'),
        depth_review_profile=request.get('depth_review_profile'), oblique=view, pose_fit=fitted,
        moving_ankles=observation, torso_projection=torso,
        on_stage=lambda stage: print(stage, flush=True))
    digest = AnimatedStore(output/'isolated-store').publish(files)
    moving = evidence['moving_ankles']
    report = dict(profile='workbench-moving-ankle-probe-v1', candidate_bundle_sha256=digest,
        parent_request_sha256=canonical_sha256(parent), request_sha256=canonical_sha256(request),
        character_sha256=request['character_sha256'], motion_identity=identity,
        status=evidence['status'], issues=evidence['issues'], geometry_passed=geometry['passed'],
        applied=moving['applied'], final_check=moving['final_check'],
        failure=moving.get('failure'), runtime_status='not_evaluated', authority='none', selected=False)
    (output/'report.json').write_bytes(canonical_bytes(report))
    print(json.dumps({k: report[k] for k in ('status','geometry_passed','applied','final_check','issues')}),flush=True)


if __name__ == '__main__':
    p=argparse.ArgumentParser()
    for name in ('state','request','output'): p.add_argument(name,type=Path)
    strategy=p.add_mutually_exclusive_group()
    strategy.add_argument('--source-pose',action='store_true')
    strategy.add_argument('--shared-yaw',type=float)
    p.add_argument('--reference-torso',action='store_true')
    a=p.parse_args();run(a.state,a.request,a.output,a.source_pose,a.shared_yaw,a.reference_torso)
