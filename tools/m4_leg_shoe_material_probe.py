"""Measure setup-overlap material separation; this is not raster seam acceptance."""
import argparse
from io import BytesIO
from hashlib import sha256
import json
from pathlib import Path
import numpy as np
from PIL import Image
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.targets.character43.active_mesh_pose import sample_active
from autospine_workbench.targets.character43.deform_addition import entries
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.targets.character43.pose_geometry_patch import _times
from m4_pose_material_review import transfer,alpha_at


def comparison_times(old,new,animation):
    old_times=_times(old['animations'][animation]);new_times=_times(new['animations'][animation])
    duration=max(old_times,default=0)
    if duration<=0 or max(new_times,default=0)!=duration:
        raise ValueError('shoe_probe_duration_changed_or_empty')
    keys=sorted(set([0.,*old_times,*new_times]))
    if len(keys)>4097:raise ValueError('shoe_probe_sample_budget')
    return sorted(set(keys+[(a+b)/2 for a,b in zip(keys,keys[1:])]))


def run(source_path,candidate_path,store,artifact,output,animation='external-motion'):
    old=json.loads(source_path.read_bytes())['skeleton'];new=json.loads(candidate_path.read_bytes())['skeleton']
    files=AnimatedStore(store).read(artifact)
    if json.loads(files['skeleton.json'])!=old:raise ValueError('shoe_probe_source_changed')
    setup=sample_active(dict(old,animations={'setup':{}}),'setup',0)
    rows=[];name=animation;times=comparison_times(old,new,name)
    frames=[(t,sample_active(old,name,t),sample_active(new,name,t)) for t in times]
    def mesh(doc,slot,attachment):return doc['skins'][0]['attachments'][slot][attachment]
    def texture(m,attachment):return np.asarray(Image.open(BytesIO(files['images/'+m.get('path',attachment)+'.png'])).convert('RGBA'))[:,:,3]
    for side in ('l','r'):
        foot='foot_'+side;shoes=[];legs=[]
        for slot,attachment in setup['attachments'].items():
            m=mesh(old,slot,attachment)
            bones={old['bones'][i]['name'] for row in entries(m) for i,w in row if w>0}
            if bones=={foot}:shoes.append(slot)
            if foot in bones and 'calf_'+side in bones:legs.append(slot)
        if len(shoes)!=1 or len(legs)!=1:raise ValueError('shoe_probe_pair_ambiguous')
        shoe,leg=shoes[0],legs[0];sm=mesh(old,shoe,setup['attachments'][shoe]);lm=mesh(old,leg,setup['attachments'][leg])
        sa=texture(sm,setup['attachments'][shoe]);la=texture(lm,setup['attachments'][leg])
        yy,xx=np.nonzero(sa>=128);uv=np.column_stack(((xx+.5)/sa.shape[1],(yy+.5)/sa.shape[0]))
        world,covered=transfer(np.asarray(sm['uvs']).reshape(-1,2),setup['vertices'][shoe],sm['triangles'],uv)
        luv=np.full_like(uv,np.nan)
        luv[covered],_=transfer(setup['vertices'][leg],np.asarray(lm['uvs']).reshape(-1,2),lm['triangles'],world[covered])
        eligible=np.flatnonzero(covered & (alpha_at(la,luv)>=128))
        if not len(eligible):
            rows.append(dict(side=side,status='no_setup_overlap_support'));continue
        ids=eligible[np.unique(np.linspace(0,len(eligible)-1,min(64,len(eligible)),dtype=int))]
        queries={shoe:uv[ids],leg:luv[ids]};samples=[]
        paths={slot:mesh(old,slot,setup['attachments'][slot]).get('path',setup['attachments'][slot]) for slot in (shoe,leg)}
        for t,old_frame,new_frame in frames:
            values=[]
            for doc,frame in ((old,old_frame),(new,new_frame)):
                locations={}
                for slot in (leg,shoe):
                    m=mesh(doc,slot,frame['attachments'][slot])
                    if m.get('path',frame['attachments'][slot])!=paths[slot]:
                        raise ValueError('shoe_probe_texture_changed')
                    points,valid=transfer(np.asarray(m['uvs']).reshape(-1,2),frame['vertices'][slot],m['triangles'],queries[slot])
                    if not valid.all():raise ValueError('shoe_probe_material_uncovered')
                    locations[slot]=points
                values.append(np.linalg.norm(locations[leg]-locations[shoe],axis=1))
            samples.append(dict(time=t,before_maximum_px=float(values[0].max()),after_maximum_px=float(values[1].max()),
                                before_median_px=float(np.median(values[0])),after_median_px=float(np.median(values[1]))))
        rows.append(dict(side=side,shoe=shoe,leg=leg,setup_overlap_pixels=len(eligible),probe_count=len(ids),
            probes={slot:dict(uv=points.tolist(),texture_path=paths[slot],
                texture_sha256=sha256(files['images/'+paths[slot]+'.png']).hexdigest()) for slot,points in queries.items()},
            samples=samples))
    report=dict(source_sha256=canonical_sha256(old),candidate_sha256=canonical_sha256(new),rows=rows,
        animation=name,sample_count=len(times),sampling='union_of_keys_and_midpoints',
        authority='none',selected=False,scope='sampled_setup_overlap_material_separation_not_alpha_gap_or_contact_acceptance')
    with output.open('x') as f:json.dump(report,f,indent=2)
    print(json.dumps(dict(output=str(output),sample_count=len(times),rows=[dict(side=r['side'],
        peak_after_px=max((s['after_maximum_px'] for s in r.get('samples',[])),default=None)) for r in rows])))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','candidate','store'):p.add_argument(n,type=Path)
    p.add_argument('artifact');p.add_argument('output',type=Path)
    p.add_argument('--animation',default='external-motion')
    a=p.parse_args();run(a.source,a.candidate,a.store,a.artifact,a.output,a.animation)
