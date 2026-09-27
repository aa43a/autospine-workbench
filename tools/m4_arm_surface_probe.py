"""Screen curved forearm hypotheses against an immutable real character candidate."""
import argparse
import json
import math
from pathlib import Path

import numpy as np

from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.motion_bundle_reader import VerifiedMotionBundleReader
from autospine_workbench.targets.character43.oblique_source import extract
from autospine_workbench.targets.character43.affine_pose import matrices, sample
from autospine_workbench.targets.character43.limb_surface_proxy import point
from autospine_workbench.asset.planning.component_local_solver import metrics


def run(state, job, slot, bone, output):
    if not job.startswith('motion-') or not job[7:].isalnum():raise ValueError('job_invalid')
    folder=state/'jobs/motion-intake-v1'/job
    request=json.loads((folder/'request.json').read_bytes())
    result=json.loads((folder/'result.json').read_bytes())
    if request.get('clip') or request.get('projection',{}).get('yaw_degrees',0):
        raise ValueError('probe_requires_original_full_view')
    if bone not in ('forearm_l','forearm_r'):raise ValueError('probe_requires_forearm')
    identity=request['motion_identity']
    bundle=VerifiedMotionBundleReader(state).load(identity['clip_sha256'],identity['bundle_sha256'])
    vectors,_,_=extract(bundle)
    times=[k['tick']/bundle.motion['ticks_per_second'] for k in next(
        t for t in bundle.motion['tracks'] if t['property']=='rotation')['keys']]
    digest=result['result']['artifact_sha256']
    files=AnimatedStore(state).read(digest);doc=json.loads(files['skeleton.json'])
    name='external-motion';setupdoc=dict(doc,animations={'setup':{}})
    setup=sample(setupdoc,'setup',0)[0][slot];rest=matrices(setupdoc,'setup',0)
    attachment=doc['skins'][0]['attachments'][slot][slot]
    data=attachment['vertices'];parsed=[];cursor=0
    while cursor<len(data):
        count=data[cursor];cursor+=1
        if type(count) is not int or count<1:raise ValueError('weighted_mesh_required')
        parsed.append([data[j:j+4] for j in range(cursor,cursor+count*4,4)]);cursor+=count*4
    m=rest[bone];scale=(m[0]*m[3]-m[1]*m[2])/math.hypot(m[0],m[2])
    widths=[abs(v*scale) for row in parsed for i,u,v,w in row if w>0 and doc['bones'][i]['name']==bone]
    if not widths:raise ValueError('forearm_influence_missing')
    radius=float(np.quantile(widths,.95))
    role='humanoid.arm.lower.'+('left' if bone.endswith('_l') else 'right')
    flat=attachment['triangles'];triangles=[flat[i:i+3] for i in range(0,len(flat),3)]
    rows=[]
    for index,time in enumerate(times):
        current=matrices(doc,name,time);before=sample(doc,name,time)[0][slot]
        raw=vectors[role][index];baseline=metrics(setup,before,triangles)
        for sign in (-1,1):
            after=[]
            for original,row in zip(before,parsed,strict=True):
                delta=np.zeros(2)
                for i,u,v,w in row:
                    if doc['bones'][i]['name']!=bone or w<=0:continue
                    m=current[bone]
                    curved=point(u,v,rest[bone],m,[raw[0],-raw[1],raw[2]],radius,sign)
                    planar=[m[0]*u+m[1]*v+m[4],m[2]*u+m[3]*v+m[5]]
                    delta+=w*(np.asarray(curved)-planar)
                after.append((np.asarray(original)+delta).tolist())
            checked=metrics(setup,after,triangles)
            rows.append(dict(time=time,front_sign=sign,before=baseline,after=checked,
                newly_failed_triangles=sorted(set(checked['bad_triangles'])-set(baseline['bad_triangles'])),
                maximum_offset=max(math.dist(a,b) for a,b in zip(before,after)),
                source_visibility=math.hypot(*raw[:2])/math.hypot(*raw)))
    report=dict(profile='additive-forearm-surface-screen-v1-experiment',source_job=job,
        candidate_sha256=digest,motion_identity=identity,slot=slot,bone=bone,radius_px=radius,
        records=rows,authority='none',selected=False,
        limitations=['radius_and_front_sign_are_hypotheses','source_keys_only_no_interpolation_check',
                     'no_new_runtime_or_depth_or_contact_check','source_texture_has_no_recovered_hidden_surface'])
    with output.open('xb') as stream:stream.write(canonical_bytes(report))
    print(json.dumps([dict(front_sign=s,
        before_failed_frames=sum(bool(r['before']['bad_triangles']) for r in rows if r['front_sign']==s),
        after_failed_frames=sum(bool(r['after']['bad_triangles']) for r in rows if r['front_sign']==s),
        regression_frames=sum(bool(r['newly_failed_triangles']) for r in rows if r['front_sign']==s),
        maximum_offset=max(r['maximum_offset'] for r in rows if r['front_sign']==s)) for s in (-1,1)]))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('state',type=Path);p.add_argument('job');p.add_argument('slot');p.add_argument('bone')
    p.add_argument('output',type=Path)
    a=p.parse_args();run(a.state,a.job,a.slot,a.bone,a.output)
