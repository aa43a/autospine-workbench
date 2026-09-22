"""Test source-depth surface lifting on exact candidate; no default/adoption changes."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import numpy as np
from m4_direction_stage_probe import load_stages
from m4_squat_stage_players import stage
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.motion_bundle_reader import VerifiedMotionBundleReader
from autospine_workbench.targets.character43.oblique_source import extract
from autospine_workbench.targets.character43.affine_pose import sample,matrices
from autospine_workbench.targets.character43.deform_addition import entries,local_delta
from autospine_workbench.targets.character43.limb_surface_proxy import point
from autospine_workbench.asset.planning.component_local_solver import metrics


def run(source,output,slots,sign,capture):
    receipt=json.loads((source/'report.json').read_bytes());identity=receipt['candidate_bundle_sha256']
    _,_,pose,_,_,parent,_=load_stages(receipt['source_job_id'])
    if parent!=receipt['source_candidate_sha256']:raise ValueError('surface_proxy_source_identity')
    request=json.loads((Path('workspace/jobs/motion-intake-v1')/receipt['source_job_id']/'request.json').read_bytes())
    if request.get('projection',{}).get('yaw_degrees',0)!=0:raise ValueError('surface_proxy_original_view_only')
    source_id=request['motion_identity'];bundle=VerifiedMotionBundleReader(Path('workspace')).load(source_id['clip_sha256'],source_id['bundle_sha256'])
    vectors,_,_=extract(bundle)
    files=AnimatedStore(source/'isolated-store').read(identity);original=json.loads(files['skeleton.json']);doc=deepcopy(original)
    name='external-motion';setupdoc=dict(doc,animations={'setup':{}});setup=sample(setupdoc,'setup',0)[0];rest=matrices(setupdoc,'setup',0)
    checks=[];radii={}
    for slot in slots:
        mesh=doc['skins'][0]['attachments'][slot][slot];influences=entries(mesh);data=mesh['vertices'];parsed=[];cursor=0
        while cursor<len(data):
            count=data[cursor];cursor+=1;parsed.append([data[j:j+4] for j in range(cursor,cursor+count*4,4)]);cursor+=count*4
        owners={doc['bones'][i]['name'] for row in influences for i,w in row if w>0};selected={n for n in owners if n.startswith(('thigh_','calf_'))}
        if len(selected)!=2:raise ValueError('surface_proxy_requires_one_leg')
        radius={}
        for n in selected:
            m=rest[n];scale=(m[0]*m[3]-m[1]*m[2])/np.hypot(m[0],m[2])
            widths=[abs(v*scale) for row in parsed for i,u,v,w in row if w>0 and doc['bones'][i]['name']==n]
            radius[n]=float(np.quantile(widths,.95))
        radii[slot]=radius;keys=[]
        for index,time in enumerate(pose['times']):
            current=matrices(original,name,time);points=[]
            for row in parsed:
                total=np.zeros(2)
                for i,u,v,w in row:
                    n=doc['bones'][i]['name'];m=current[n]
                    if n in selected:
                        side='left' if n.endswith('_l') else 'right';part='upper' if n.startswith('thigh_') else 'lower'
                        raw=vectors[f'humanoid.leg.{part}.{side}'][index]
                        p=point(u,v,rest[n],m,[raw[0],-raw[1],raw[2]],radius[n],sign)
                    else:p=[m[0]*u+m[1]*v+m[4],m[2]*u+m[3]*v+m[5]]
                    total+=w*np.asarray(p)
                points.append(total.tolist())
            bare=deepcopy(original);bare['animations'][name].get('attachments',{}).get('default',{}).pop(slot,None)
            before=sample(bare,name,time)[0][slot]
            keys.append(dict(time=time,vertices=[float(v) for v in local_delta(doc,influences,current,before,points)]))
        doc['animations'][name].setdefault('attachments',{}).setdefault('default',{})[slot]={slot:dict(deform=keys)}
    if doc['animations'][name]['bones']!=original['animations'][name]['bones']:
        raise ValueError('surface_proxy_bones_changed')
    if doc['skins']!=original['skins'] or doc['slots']!=original['slots']:
        raise ValueError('surface_proxy_setup_changed')
    for time in (0.,.966667,1.12):
        old=sample(original,name,time)[0];new=sample(doc,name,time)[0]
        if any(old[n]!=new[n] for n in old if n not in slots):raise ValueError('surface_proxy_other_attachment_changed')
        for slot in slots:
            flat=doc['skins'][0]['attachments'][slot][slot]['triangles'];tri=[flat[i:i+3] for i in range(0,len(flat),3)]
            checks.append(dict(slot=slot,time=time,before=metrics(setup[slot],old[slot],tri),after=metrics(setup[slot],new[slot],tri)))
    output.mkdir(parents=True,exist_ok=False)
    (output/'probe.json').write_bytes(canonical_bytes(dict(source=identity,source_identity=source_id,front_sign=sign,radii=radii,checks=checks,
        selected=False,authority='none',limitations=['cylindrical_radius_is_hypothesis','front_side_unreviewed','no_depth_order_changes','source_frame_bake_not_dense_validation'])))
    print(json.dumps([dict(slot=r['slot'],time=r['time'],old=r['before']['inversions'],new=r['after']['inversions']) for r in checks]),flush=True)
    if capture:stage(doc,files,[0.,.966667,1.12],output/'trial',identity)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path);p.add_argument('output',type=Path)
    p.add_argument('--slots',nargs='+',required=True);p.add_argument('--front-sign',type=int,choices=(-1,1),required=True);p.add_argument('--capture',action='store_true')
    a=p.parse_args();run(a.source,a.output,a.slots,a.front_sign,a.capture)
