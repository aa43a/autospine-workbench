"""Exact-source absolute leg pose comparison; independent experimental assets."""
import argparse
from copy import deepcopy
import json
import math
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.motion_bundle_reader import VerifiedMotionBundleReader
from autospine_workbench.targets.character43.oblique_source import extract
from autospine_workbench.targets.character43.source_pose_fit import fit
from autospine_workbench.targets.character43.root_pivot_candidate import build
from autospine_workbench.targets.character43.source_ankle_targets import targets
from autospine_workbench.targets.character43.affine_pose import matrices
from autospine_workbench.targets.spine43.continuous_pose import interpolate
from autospine_workbench.resolved_project import canonical_sha256


def run(artifact, output, artifact_state=Path('workspace')):
    files = AnimatedStore(artifact_state).read(artifact)
    document = json.loads(files['skeleton.json'])
    moving = json.loads(files['motion-moving-ankles.json'])
    observation = moving['source_observation']
    if observation['yaw_degrees'] != 0 or moving['applied']:
        raise ValueError('requires_unapplied_zero_additional_yaw')
    if canonical_sha256(document) != moving['input_skeleton_sha256']:
        raise ValueError('input_skeleton_changed')
    bundle = VerifiedMotionBundleReader(Path('workspace')).load(observation['motion_sha256'], observation['source_bundle_sha256'])
    vectors, _, _ = extract(bundle)
    times = observation['times']
    name = next(iter(document['animations']))
    legs = {k: v for k, v in vectors.items() if k.startswith('humanoid.leg.')}
    fitted, fit_report = fit(document, name, legs, times)
    dense = sorted(set(times) | {(a+b)/2 for a, b in zip(times, times[1:])})
    pivot, pivot_report = build(fitted, name, dense)
    # An explicit alternative length policy, never a silent removal from input.
    projection_input = deepcopy(document)
    replaced_scales = {}
    for bone in ('thigh_l', 'calf_l', 'thigh_r', 'calf_r'):
        channels = projection_input['animations'][name]['bones'].get(bone, {})
        replaced_scales[bone] = channels.pop('scale', [])
    projected, projection_report = fit(projection_input, name, legs, times, project_lengths=True)
    projected_pivot, projected_pivot_report = build(projected, name, dense)
    reference = moving['final_check']['limit_px']/.01
    sample_times = sorted(set(dense) | {(a+b)/2 for a, b in zip(dense, dense[1:])})
    records = {}
    variants = {'original': document, 'absolute_legs': fitted, 'absolute_legs_pelvis_pivot': pivot}
    variants.update(absolute_projection=projected, absolute_projection_pelvis_pivot=projected_pivot)
    for label, doc in variants.items():
        initial = matrices(doc, name, 0)
        trajectory = targets(observation, [initial['foot_'+s][4:6] for s in ('l','r')], reference)
        feet = [[dict(time=r['time'], vertices=r['targets'][i]) for r in trajectory] for i in (0,1)]
        errors = [dict(time=t, side=s, error_px=math.dist(matrices(doc,name,t)['foot_'+s][4:6],
                                                       interpolate(feet[i],t,'vertices')))
                  for t in sample_times for i,s in enumerate(('l','r'))]
        records[label] = dict(skeleton_sha256=canonical_sha256(doc),
            initial_feet={s:list(initial['foot_'+s][4:6]) for s in ('l','r')},
            samples=len(sample_times), worst=max(errors,key=lambda r:r['error_px']),
            rms=math.sqrt(sum(r['error_px']**2 for r in errors)/len(errors)))
    report = dict(source_artifact=artifact, source_observation=observation,
                  variants=records, fit=fit_report, pivot=pivot_report, selected=False, authority='none',
                  projection=projection_report, projected_pivot=projected_pivot_report,
                  replaced_relative_scale_channels=replaced_scales,
                  scope='own_initial_ankle_displacement_comparison_not_setup_visual_or_runtime_acceptance')
    output.mkdir()
    for label, doc in variants.items():
        with (output/(label+'.json')).open('x',encoding='utf-8') as stream:
            json.dump(doc,stream)
    with (output/'report.json').open('x',encoding='utf-8') as stream:
        json.dump(report,stream,indent=2)
    print(json.dumps(records))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('artifact')
    parser.add_argument('output',type=Path)
    parser.add_argument('--artifact-state',type=Path,default=Path('workspace'))
    args=parser.parse_args()
    run(args.artifact,args.output,args.artifact_state)
