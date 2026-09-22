"""Publish an isolated three-surface knee experiment using only source texels."""
import argparse
from copy import deepcopy
import json
import math
from pathlib import Path
import numpy as np
from m4_direction_stage_probe import load_stages
from m4_squat_stage_players import stage
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.affine_pose import matrices,sample
from autospine_workbench.targets.character43.deform_addition import entries,local_delta
from autospine_workbench.targets.character43.transverse_frame import without_inherited_shear
from autospine_workbench.targets.character43.joint_material_strip import relative
from autospine_workbench.targets.character43.pivot_frame_blend import blend
from autospine_workbench.targets.character43.material_band_partition import partition
from autospine_workbench.targets.character43.skirt_candidate import inverse
from autospine_workbench.targets.spine43.continuous_pose import area
from autospine_workbench.asset.planning.component_local_solver import metrics


def run(source,output,slots):
    receipt=json.loads((source/'report.json').read_bytes());identity=receipt['candidate_bundle_sha256']
    _,_,pose,_,_,parent,_=load_stages(receipt['source_job_id'])
    if parent!=receipt['source_candidate_sha256']:raise ValueError('segmented_knee_source_mismatch')
    files=AnimatedStore(source/'isolated-store').read(identity);original=json.loads(files['skeleton.json']);doc=deepcopy(original)
    name='external-motion';animation=doc['animations'][name]
    if animation.get('drawOrder') or animation.get('slots'):raise ValueError('segmented_knee_order_unsupported')
    setupdoc=dict(original,animations={'setup':{}});setup=sample(setupdoc,'setup',0)[0];rest=matrices(setupdoc,'setup',0)
    bones={b['name']:i for i,b in enumerate(doc['bones'])};records=[];coverage=[]
    for slot in slots:
        mesh=original['skins'][0]['attachments'][slot][slot];owners=entries(mesh)
        knees={original['bones'][i]['name'] for row in owners for i,w in row if w>0 and original['bones'][i]['name'].startswith('calf_')}
        if len(knees)!=1:raise ValueError('segmented_knee_unique_joint_required')
        knee=knees.pop();upper=doc['bones'][bones[knee]]['parent'];center=np.array(rest[knee][4:]);axis=center-np.array(rest[upper][4:]);length=np.linalg.norm(axis);axis/=length
        normal=np.array([-axis[1],axis[0]]);points=setup[slot]
        near=[abs(float((np.array(p)-center)@normal)) for p in points if abs(float((np.array(p)-center)@axis))<.15*length]
        if not near:raise ValueError('segmented_knee_cross_section_missing')
        radius=float(np.quantile(near,.9))
        if not 1<radius<length*.5:raise ValueError('segmented_knee_cover_out_of_range')
        tri=[mesh['triangles'][i:i+3] for i in range(0,len(mesh['triangles']),3)]
        uvs=[mesh['uvs'][i:i+2] for i in range(0,len(mesh['uvs']),2)]
        parts=partition(points,uvs,tri,center,axis,[-radius,radius])
        old_area=sum(area(points,t) for t in tri);new_area=sum(area(p['points'],t) for p in parts for t in p['triangles'])
        if abs(old_area-new_area)>max(1e-6,abs(old_area)*1e-9):raise ValueError('segmented_knee_setup_area_mismatch')
        coverage.append(dict(slot=slot,radius_px=radius,source_area=old_area,partition_area=new_area))
        oldslot=next(s for s in doc['slots'] if s['name']==slot);newslots=[]
        del doc['skins'][0]['attachments'][slot]
        animation.get('attachments',{}).get('default',{}).pop(slot,None)
        # Joint cover is in front of both segments inside the original slot's
        # position. This is an explicit experiment, not inferred source depth.
        for index in (0,2,1):
            part=parts[index];partname=slot+'-surface-'+str(index)
            if not part['triangles']:raise ValueError('segmented_knee_empty_surface')
            if partname in doc['skins'][0]['attachments']:raise ValueError('segmented_knee_collision')
            newslots.append(dict(oldslot,name=partname,attachment=partname));newmesh=deepcopy(mesh)
            newmesh.pop('hull',None);newmesh.pop('edges',None);newmesh['path']=mesh.get('path',slot)
            newmesh['uvs']=[v for uv in part['uvs'] for v in uv];newmesh['triangles']=[v for t in part['triangles'] for v in t]
            newmesh['vertices']=[v for p in part['points'] for v in (1,bones['root'],*inverse(rest['root'],p),1.)]
            doc['skins'][0]['attachments'][partname]={partname:newmesh};influences=entries(newmesh);keys=[]
            for time in pose['times']:
                current=matrices(original,name,time)
                frames=[relative(rest[n],without_inherited_shear(rest[n],current[n])[0]) for n in (upper,knee)]
                def transform(frame,p):
                    a,b,c,d,x,y=frame;return [a*p[0]+b*p[1]+x,c*p[0]+d*p[1]+y]
                target=[blend(p,center,frames,[.5,.5]) if index==1 else transform(frames[0 if index==0 else 1],p) for p in part['points']]
                base=[transform(relative(rest['root'],current['root']),p) for p in part['points']]
                keys.append(dict(time=time,vertices=[float(v) for v in local_delta(doc,influences,current,base,target)]))
            animation.setdefault('attachments',{}).setdefault('default',{})[partname]={partname:dict(deform=keys)}
            records.append(dict(source_slot=slot,slot=partname,surface=index,triangles=len(part['triangles']),points=part['points']))
        at=doc['slots'].index(oldslot);doc['slots'][at:at+1]=newslots
    times=sorted(set(pose['times'])|{(a+b)/2 for a,b in zip(pose['times'],pose['times'][1:])})
    checks=[]
    for time in (0.,.966667,1.12):
        world=sample(doc,name,time)[0]
        for r in records:
            m=doc['skins'][0]['attachments'][r['slot']][r['slot']];tri=[m['triangles'][i:i+3] for i in range(0,len(m['triangles']),3)]
            checks.append(dict(slot=r['slot'],time=time,**metrics(r['points'],world[r['slot']],tri)))
    if animation['bones']!=original['animations'][name]['bones']:raise ValueError('segmented_knee_bones_changed')
    output.mkdir(parents=True,exist_ok=False)
    (output/'probe.json').write_bytes(canonical_bytes(dict(profile='segmented-knee-source-surfaces-v1',source=identity,
        authority='none',selected=False,coverage=coverage,checks=checks,
        limitations=['setup_area_uv_conservation_not_pixel_capture_proof','joint_front_order_is_experimental',
                     'ankle_contact_and_dynamic_overlap_not_validated','not_parent_full_dense_sample_grid'])))
    print(json.dumps(dict(surfaces=len(records),maximum_inversions=max(r['inversions'] for r in checks))),flush=True)
    stage(doc,files,times,output/'trial',identity)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path);p.add_argument('output',type=Path)
    p.add_argument('--slots',nargs='+',required=True);a=p.parse_args();run(a.source,a.output,a.slots)
