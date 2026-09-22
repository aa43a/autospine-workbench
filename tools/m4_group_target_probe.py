"""Isolated character key-pose test of source-anchored leg directions."""
import argparse
from copy import deepcopy
import json
import math
from pathlib import Path

from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.motion_bundle_reader import VerifiedMotionBundleReader
from autospine_workbench.targets.character43.group_projection_pose import source_segments, pose
from autospine_workbench.targets.character43.group_projection_lengths import constrain
from autospine_workbench.targets.character43.source_pose_fit import fit
from autospine_workbench.targets.character43.affine_pose import matrices
from m4_squat_stage_players import stage


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--branch', type=int, choices=(-1, 1), required=True)
    args = parser.parse_args()
    receipt = json.loads((args.source/'report.json').read_bytes())
    identity = receipt['motion_identity']
    bundle = VerifiedMotionBundleReader(Path('workspace')).load(identity['clip_sha256'], identity['bundle_sha256'])
    segments = source_segments(bundle)
    keys = next(t for t in bundle.motion['tracks'] if t['property'] == 'rotation')['keys']
    times = [k['tick']/bundle.motion['ticks_per_second'] for k in keys]
    vectors = {r: [] for r in segments if r.startswith('humanoid.leg.') and '.foot.' not in r}
    for i in range(len(times)):
        original = pose(segments, i, {})
        projected = pose(segments, i, {'leg.left': -90, 'leg.right': -90})
        constrained, failures, _ = constrain(original, projected, segments, i, args.branch, length_mode='source_lengths')
        if failures: raise ValueError('source_group_target_unreachable')
        for role in vectors:
            row = constrained[role]
            vectors[role].append([row['end'][0]-row['start'][0], row['end'][1]-row['start'][1], 0.])
    parent = receipt['candidate_bundle_sha256']
    files = AnimatedStore(args.source/'isolated-store').read(parent)
    baseline = json.loads(files['skeleton.json'])
    uncorrected = deepcopy(baseline)
    animation = uncorrected['animations']['external-motion']
    animation.pop('attachments', None)
    animation.pop('deform', None)
    for name in ('thigh_l', 'calf_l', 'thigh_r', 'calf_r'):
        animation['bones'][name].pop('scale', None)
    candidate, evidence = fit(uncorrected, 'external-motion', vectors, times)
    # Endpoint errors are target-space diagnostics, never claim source locks survived retargeting.
    errors = []
    for time in times:
        before, after = [matrices(d, 'external-motion', time) for d in (baseline, candidate)]
        errors.extend(dict(time=time, bone=bone, displacement_px=math.dist(before[bone][4:6], after[bone][4:6]))
                      for bone in ('foot_l', 'foot_r'))
    args.output.mkdir(parents=True, exist_ok=False)
    report = dict(authority='none', selected=False, parent=parent, source_identity=identity,
        branch=args.branch, source_pose_fit=evidence, ankle_displacements=errors,
        maximum_ankle_displacement_px=max(r['displacement_px'] for r in errors),
        limitations=['source_ankle_constraints_not_preserved_by_direction_only_target_fit',
                    'old_corrective_deforms_removed_for_diagnostic',
                    'key_pose_runtime_only_not_full_clip_acceptance'])
    (args.output/'probe.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    stage(candidate, files, [times[0], times[len(times)//2], times[-1]], args.output/'candidate', parent)
    from autospine_workbench.targets.character43.group_target_contact import constrain as target_constrain
    corrected, contact = target_constrain(candidate, baseline, times)
    (args.output/'target-contact.json').write_text(json.dumps(contact, indent=2), encoding='utf-8')
    stage(corrected, files, [times[0], times[len(times)//2], times[-1]], args.output/'target-contact', parent)
    print(json.dumps(dict(maximum_ankle_displacement_px=report['maximum_ankle_displacement_px'])))


if __name__ == '__main__': main()
