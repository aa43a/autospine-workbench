"""Compare source projection capacity without selecting a new view or changing artwork."""
import argparse
import json
import math
from pathlib import Path
from autospine_workbench.automation.motion_target_pose import prepare
from autospine_workbench.motion_bundle_reader import VerifiedMotionBundleReader
from autospine_workbench.targets.character43.oblique_motion import project


def run(job):
    request=json.loads((Path('workspace/jobs/motion-intake-v1')/job/'request.json').read_bytes())
    identity=request['motion_identity']
    bundle=VerifiedMotionBundleReader(Path('workspace')).load(identity['clip_sha256'],identity['bundle_sha256'])
    pose=prepare(bundle);rows=[]
    for yaw in (-45,-30,-15,0,15,30,45):
        limbs=[]
        for role,vectors in pose['vectors'].items():
            if not role.startswith(('humanoid.arm.upper.','humanoid.arm.lower.','humanoid.leg.upper.','humanoid.leg.lower.')):continue
            values=[math.hypot(*project(v,yaw)[:2])/math.hypot(*v) for v in vectors]
            index=min(range(len(values)),key=values.__getitem__)
            limbs.append(dict(role=role,minimum_visibility=values[index],worst_time=pose['times'][index],
                below_half_length=sum(v<.5 for v in values),unreliable_samples=sum(v<.2 for v in values)))
        rows.append(dict(yaw=yaw,limbs=limbs,minimum_visibility=min(r['minimum_visibility'] for r in limbs),
            all_limb_samples_above_half=all(r['minimum_visibility']>=.5 for r in limbs)))
    return dict(job=job,motion_identity=identity,rows=rows,authority='none',selected=False,
        scope='source_vector_projection_only_not_target_mesh_contact_artwork_or_visual_acceptance')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path);p.add_argument('jobs',nargs='+')
    a=p.parse_args();results=[run(job) for job in a.jobs]
    with a.output.open('x',encoding='utf-8') as f:json.dump(results,f,indent=2)
    for result in results:
        print(json.dumps(dict(job=result['job'],views=[{k:v for k,v in r.items() if k!='limbs'} for r in result['rows']])))
