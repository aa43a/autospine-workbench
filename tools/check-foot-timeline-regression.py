"""Replay admitted foot observations on an immutable candidate; numeric audit only."""
import argparse
from copy import deepcopy
import json
import math
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.targets.character43.affine_pose import matrices
from autospine_workbench.targets.character43.foot_orientation_fit import fit
from autospine_workbench.targets.character43.foot_orientation_timeline import angle_at


def main():
    parser=argparse.ArgumentParser();parser.add_argument('target');parser.add_argument('output')
    args=parser.parse_args();target=Path(args.target);output=Path(args.output)
    if output.exists():raise ValueError('output_exists')
    identity=json.loads((target/'report.json').read_bytes())['candidate_bundle_sha256']
    files=AnimatedStore(target/'isolated-store').read(identity)
    original=json.loads(files['skeleton.json']);review=json.loads(files['motion-review.json'])
    observation=review['post_contact_repair']['observations'];name='external-motion'
    bare=deepcopy(original)
    for bone in observation['tracks']:
        for channel in ('rotate','scale','shear'):
            bare['animations'][name]['bones'][bone].pop(channel,None)
    result,report=fit(bare,name,observation)
    setup=deepcopy(bare);setup['animations'][name]={'bones':{}}
    rest=matrices(setup,name,0);errors={'before':0.,'after':0.};ankle=0.
    for index in range(1001):
        t=observation['times'][-1]*index/1000
        old=matrices(original,name,t);new=matrices(result,name,t)
        for bone,values in observation['tracks'].items():
            theta=math.radians(angle_at(observation['times'],values,t));co,si=math.cos(theta),math.sin(theta);r=rest[bone]
            wanted=(co*r[0]-si*r[2],co*r[1]-si*r[3],si*r[0]+co*r[2],si*r[1]+co*r[3])
            for key,posed in [('before',old),('after',new)]:
                errors[key]=max(errors[key],max(abs(x-y) for x,y in zip(wanted,posed[bone][:4]))/max(abs(v) for v in r[:4]))
            ankle=max(ankle,math.dist(old[bone][4:],new[bone][4:]))
    output.mkdir(parents=True)
    summary=dict(parent_artifact=identity,fit=report,dense_samples=1001,maximum_relative_matrix_error=errors,
                 maximum_ankle_displacement=ankle,authority='none',
                 scope='numeric_replay_not_runtime_geometry_or_visual_acceptance')
    (output/'report.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps(summary))


if __name__=='__main__':main()
