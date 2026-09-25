"""Run explicitly requested local diagnostics against the new repair artifact."""
import json
from ..motion_bundle_reader import VerifiedMotionBundleReader
from ..targets.character43.local_depth_analysis import PROFILE, analyze
from ..targets.character43.depth_sample_times import repair_times
from .motion_local_depth_evidence import publish


def run(files, artifact, request, state_root, folder, on_progress):
    if not request.get('local_depth_profile'):
        return None
    if request['local_depth_profile'] != PROFILE:
        raise ValueError('motion_local_depth_profile_unsupported')
    identity = request['motion_identity']
    bundle = VerifiedMotionBundleReader(state_root).load(identity['clip_sha256'],identity['bundle_sha256'])
    document = json.loads(files['skeleton.json'])
    depth = json.loads(files['motion-depth.json'])
    try:
        on_progress()
        times = repair_times(document,request['repair_execution']['draft']['animation'],depth)
        report = analyze(files,artifact,bundle,request,sample_times=times,on_pair=on_progress,triangle_traces=True)
    except ValueError as error:
        report = dict(profile=PROFILE,job_id=request['job_id'],artifact_sha256=artifact,
            authority='none',selected=False,records=[],interpolation='not_evaluated',
            failure=str(error),scope='supplemental_check_failed_not_acceptance')
    return publish(state_root,folder,request,artifact,report)
