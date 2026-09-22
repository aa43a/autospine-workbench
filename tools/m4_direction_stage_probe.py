"""Attribute direction changes to verified pre-contact fit or final bone tracks."""
import argparse
from copy import deepcopy
import json
import math
from pathlib import Path

from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.motion_pose_policy import prepare
from autospine_workbench.automation.motion_target_pose import project
from autospine_workbench.motion_bundle_reader import VerifiedMotionBundleReader
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.targets.character43.motionir_candidate import build
from autospine_workbench.targets.character43.motion_direction_audit import audit
from autospine_workbench.targets.character43.affine_pose import matrices
from autospine_workbench.targets.character43.joint_support_solver import solve
from autospine_workbench.targets.spine43.continuous_pose import interpolate


def support_probe(fitted, final, contact, time, reference):
    active = [a for a in contact['phase_attempt']['anchors'] if a['start'] <= time < a['end']]
    requested = []
    for a in active:
        side = 'l' if a['limb'] == 'leg.left' else 'r'
        requested.append(dict(upper='thigh_'+side, lower='calf_'+side, tip='foot_'+side, target=a['target']))
    if not requested:
        return dict(time=time, status='no_active_contacts')
    existing = matrices(final, 'external-motion', time)
    previous_residual = max(math.dist(existing[c['tip']][4:6], c['target']) for c in requested)
    report = solve(fitted, 'external-motion', time, requested, reference, preserve_pose=True,
                   maximum_error_px=min(.01*reference, max(1e-6, previous_residual)))
    if report['solution'] is None:
        return dict(time=time, solver=report)
    doc = deepcopy(fitted); tracks = doc['animations']['external-motion']['bones']
    root = tracks['root']['translate']
    xy = interpolate([dict(time=k['time'], vertices=[k['x'], k['y']]) for k in root], time, 'vertices')
    shift = report['solution']['root_shift']
    tracks['root']['translate'] = [dict(time=0, x=xy[0]+shift[0], y=xy[1]+shift[1])]
    for leg in report['solution']['legs']:
        for part in ('upper', 'lower'):
            bone = leg[part]
            value = interpolate(tracks[bone]['rotate'], time, 'value')+leg[part+'_delta_degrees']
            tracks[bone]['rotate'] = [dict(time=0, value=value)]
    before, old, new = [matrices(d, 'external-motion', time) for d in (fitted, final, doc)]
    def error(a, b):
        return abs((math.degrees(math.atan2(a[2], a[0])-math.atan2(b[2], b[0]))+180)%360-180)
    return dict(time=time, previous_maximum_endpoint_error_px=previous_residual, solver=report,
                axes=[dict(bone=n, previous_error_deg=error(old[n], before[n]),
                candidate_error_deg=error(new[n], before[n])) for n in ('thigh_l','calf_l','thigh_r','calf_r')],
                scope='single_pose_without_temporal_mesh_or_runtime_validation')


def load_stages(job):
    root = Path('workspace/jobs/motion-intake-v1') / job
    request = json.loads((root/'request.json').read_bytes())
    result = json.loads((root/'result.json').read_bytes())
    if result['status'] != 'succeeded':
        raise ValueError('stage_probe_job_not_successful')
    identity = request['motion_identity']
    bundle = VerifiedMotionBundleReader(Path('workspace')).load(identity['clip_sha256'], identity['bundle_sha256'])
    pose = prepare(bundle, request)
    if pose is None:
        raise ValueError('stage_probe_requires_explicit_pose_strategy')
    store = AnimatedStore('workspace')
    source = json.loads(store.read(request['character_sha256'])['skeleton.json'])
    source['animations'] = {}
    baseline, _ = build(source, bundle.motion, 'external-motion')
    fitted, evidence = project(baseline, 'external-motion', bundle.motion, None, None, None, None, None, pose)
    artifact = result['result']['artifact_sha256']
    files = store.read(artifact)
    review = json.loads(files['motion-review.json'])
    if canonical_sha256(fitted) != review['source_pose_fit']['output_sha256']:
        raise ValueError('stage_probe_fitted_identity_changed')
    final = json.loads(files['skeleton.json'])
    return fitted, final, pose, review, files, artifact, bundle.motion


def run(job):
    fitted, final, pose, review, files, artifact, motion = load_stages(job)
    before = audit(fitted, 'external-motion', pose['vectors'], pose['times'])
    after = audit(final, 'external-motion', pose['vectors'], pose['times'])
    worst = max((r['worst_direction'] for r in after['records'] if r['bone'].startswith(('thigh','calf'))),
                key=lambda r:r['error_deg'])
    probe = support_probe(fitted, final, json.loads(files['motion-contact.json']), worst['time'], review['reference_length_px'])
    unchanged = []
    for record in after['records']:
        bone = record['bone']
        if fitted['animations']['external-motion']['bones'][bone] == final['animations']['external-motion']['bones'][bone]:
            unchanged.append(bone)
    return dict(job_id=job, artifact_sha256=artifact, authority='none',
        pre_contact_fit_sha256=canonical_sha256(fitted), pre_contact=before, final=after,
        unchanged_local_bone_tracks=unchanged,
        pose_preserving_support_probe=probe,
        scope='verified_stage_direction_difference_not_visual_or_causal_proof')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('jobs', nargs='+')
    args = parser.parse_args()
    reports = [run(job) for job in args.jobs]
    with args.output.open('x', encoding='utf-8') as handle:
        json.dump(reports, handle, indent=2)
    for r in reports:
        print(r['job_id'], 'unchanged', r['unchanged_local_bone_tracks'])
        for a, b in zip(r['pre_contact']['records'], r['final']['records']):
            print(a['bone'], a['worst_direction']['error_deg'], b['worst_direction']['error_deg'])
