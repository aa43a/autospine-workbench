"""Full-character Runtime regression for temporally refined foot frames."""
import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.affine_pose import sample
from autospine_workbench.targets.character43.deformation_qa import inspect
from autospine_workbench.targets.character43.final_motion_contact import recheck
from autospine_workbench.targets.character43.foot_orientation_fit import fit
from autospine_workbench.targets.character43.numeric_reference import read, write
from m4_squat_stage_players import stage


def main():
    parser=argparse.ArgumentParser();parser.add_argument('source',type=Path);parser.add_argument('output',type=Path)
    args=parser.parse_args()
    if args.output.exists():raise ValueError('output_exists')
    receipt=json.loads((args.source/'report.json').read_bytes());parent=receipt['candidate_bundle_sha256']
    files=AnimatedStore(args.source/'isolated-store').read(parent)
    original=json.loads(files['skeleton.json']);review=json.loads(files['motion-review.json'])
    observation=review['post_contact_repair']['observations'];name='external-motion'
    bare=deepcopy(original)
    for bone in observation['tracks']:
        for channel in ('rotate','scale','shear'):
            bare['animations'][name]['bones'][bone].pop(channel,None)
    result,fit_report=fit(bare,name,observation)
    # Verify that no corrective deform, draw order, texture or unrelated bone changes.
    untouched=deepcopy(result)
    for bone in observation['tracks']:
        untouched['animations'][name]['bones'][bone]=deepcopy(original['animations'][name]['bones'][bone])
    if untouched!=original:raise ValueError('foot_probe_changed_other_channels')
    reference=read(files)
    if reference['skeleton_sha256']!=sha256(files['skeleton.json']).hexdigest():raise ValueError('reference_mismatch')
    knots=sorted({key.get('time',0) for bone in observation['tracks']
                  for key in result['animations'][name]['bones'][bone]['rotate']})
    times=sorted({row['time'] for row in reference['animations'][name]}|set(knots)|
                 {a+(b-a)*f for a,b in zip(knots,knots[1:]) for f in (.25,.5,.75)})
    if len(times)>4097:raise ValueError('foot_probe_sample_limit')
    args.output.mkdir(parents=True)
    baseline=write(files,dict(skeleton_sha256=sha256(files['skeleton.json']).hexdigest(),
        animations={name:[dict(time=t,vertices=sample(original,name,t)[0]) for t in times]}))
    before=inspect(baseline,setup_vertices=json.loads(files['rig-setup-reference.json'])['vertices'])
    (args.output/'before-geometry.json').write_bytes(canonical_bytes(before))
    print(json.dumps(dict(stage='baseline_geometry',frames=len(times),passed=before['passed'])),flush=True)
    candidate=stage(result,files,times,args.output/'candidate',parent)
    after=json.loads((args.output/'candidate/runtime/deformation.json').read_bytes())
    previous={row['slot']:row for row in before['records']}
    delta=[dict(slot=row['slot'],before_failed_frames=previous[row['slot']]['failing_frame_count'],
                after_failed_frames=row['failing_frame_count'],
                before_inversions=previous[row['slot']]['inversion_samples'],after_inversions=row['inversion_samples'],
                before_max_area=previous[row['slot']]['max_area_ratio'],after_max_area=row['max_area_ratio'])
           for row in after['records']]
    contact=recheck(result,name,json.loads(files['motion-ir.json']),json.loads(files['motion-contact.json']),
                    times,review['reference_length_px'])
    report=dict(parent_artifact=parent,candidate_artifact=candidate,fit=fit_report,sample_count=len(times),
        geometry_before=before,geometry_after=after,geometry_comparison=delta,contact=contact,authority='none',selected=False,
        unchanged_other_channels=True,depth_status='not_rechecked',visual_status='not_reviewed',
        scope='whole_character_sampled_regression_not_adoption')
    (args.output/'report.json').write_bytes(canonical_bytes(report))
    print(json.dumps(dict(candidate=candidate,frames=len(times),geometry_passed=after['passed'],contact=contact['status'])),flush=True)


if __name__=='__main__':main()
