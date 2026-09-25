"""Compare source garment coverage and animated limb material without editing."""
import argparse
from copy import deepcopy
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import numpy as np
from PIL import Image
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.affine_pose import sample
from autospine_workbench.targets.character43.deform_addition import entries


def exposure_kind(frame_alpha,setup_cloth_alpha,current_cloth_alpha):
    if frame_alpha<8:return 'not_visible_in_captured_frame'
    if current_cloth_alpha>=8:return 'current_cloth_overlap_requires_composite_review'
    if setup_cloth_alpha>=8:return 'newly_exposed_source_covered_material'
    return 'previously_visible_limb_material'


def coverage(mesh,points,texture,query):
    uv=np.asarray(mesh['uvs']).reshape(-1,2);alphas=[]
    for ids in np.asarray(mesh['triangles']).reshape(-1,3):
        a,b,c=np.asarray(points)[ids];matrix=np.column_stack((b-a,c-a))
        if abs(np.linalg.det(matrix))<1e-12:continue
        w=np.linalg.solve(matrix,np.asarray(query)-a);w=np.r_[1-w.sum(),w]
        if min(w)<-1e-8:continue
        tex=w@uv[ids];x=tex[0]*texture.width-.5;y=tex[1]*texture.height-.5
        ix,iy=int(np.floor(x)),int(np.floor(y));fx,fy=x-ix,y-iy;alpha=0.
        for dx,dy,weight in ((0,0,(1-fx)*(1-fy)),(1,0,fx*(1-fy)),(0,1,(1-fx)*fy),(1,1,fx*fy)):
            alpha+=weight*texture.getpixel((min(texture.width-1,max(0,ix+dx)),min(texture.height-1,max(0,iy+dy))))[3]
        alphas.append(float(alpha))
    return max(alphas,default=0.)


def run(source,trace_path,limb,cloth,output):
    if output.exists():raise ValueError('cloth_limb_probe_output_exists')
    receipt=json.loads((source/'report.json').read_bytes());files=AnimatedStore(source/'isolated-store').read(receipt['candidate_bundle_sha256'])
    trace=json.loads(trace_path.read_bytes());setup=json.loads(files['rig-setup-reference.json'])
    digest=sha256(files['skeleton.json']).hexdigest()
    if trace['candidate_bundle_sha256']!=receipt['candidate_bundle_sha256'] or trace['skeleton_sha256']!=digest or setup['skeleton_sha256']!=digest:
        raise ValueError('cloth_limb_probe_identity')
    doc=json.loads(files['skeleton.json']);time=trace['time'];name='external-motion'
    current=sample(doc,name,time)[0];without=deepcopy(doc)
    without['animations'][name].get('attachments',{}).get('default',{}).pop(limb,None)
    uncorrected=sample(without,name,time)[0];mesh=doc['skins'][0]['attachments'][limb][limb]
    garment=doc['skins'][0]['attachments'][cloth][cloth]
    texture=Image.open(BytesIO(files['images/'+garment.get('path',cloth)+'.png'])).convert('RGBA')
    influences=entries(mesh);rows=[]
    for row in trace['rows']:
        hit=next(h for h in row['hits'] if h['slot']==limb)
        ids=mesh['triangles'][3*hit['triangle']:3*hit['triangle']+3]
        a,b,c=np.asarray(current[limb])[ids];w=np.linalg.solve(np.column_stack((b-a,c-a)),np.asarray(row['world'])-a);w=np.r_[1-w.sum(),w]
        if min(w)<-1e-8:raise ValueError('cloth_limb_probe_triangle_mismatch')
        original=w@np.asarray(setup['vertices'][limb])[ids];uncorrected_world=w@np.asarray(uncorrected[limb])[ids]
        weights={}
        for v,coef in zip(ids,w):
            for index,weight in influences[v]:
                bone=doc['bones'][index]['name'];weights[bone]=weights.get(bone,0.)+float(coef*weight)
        prior=coverage(garment,setup['vertices'][cloth],texture,original)
        after=coverage(garment,current[cloth],texture,row['world'])
        rows.append(dict(pixel=row['pixel'],framebuffer_rgba=row['framebuffer_rgba'],triangle=hit['triangle'],
            source_material_world=original.tolist(),current_world=row['world'],without_leg_deform_world=uncorrected_world.tolist(),
            leg_deform_displacement_px=float(np.linalg.norm(uncorrected_world-row['world'])),bone_weights=weights,
            setup_cloth_alpha=prior,current_cloth_alpha=after,
            exposure_kind=exposure_kind(row['framebuffer_rgba'][3],prior,after),
            source_covered_now_exposed=row['framebuffer_rgba'][3]>=8 and prior>=8 and after<8))
    cloth_bones=sorted({doc['bones'][i]['name'] for row in entries(garment) for i,w in row if w>0})
    result=dict(candidate_bundle_sha256=trace['candidate_bundle_sha256'],skeleton_sha256=digest,time=time,
        trace_sha256=sha256(trace_path.read_bytes()).hexdigest(),limb=limb,cloth=cloth,cloth_weight_bones=cloth_bones,rows=rows,
        authority='none',selected=False,scope='sampled_material_coverage_change_not_3d_collision_or_garment_semantic_proof')
    output.write_bytes(canonical_bytes(result));print(json.dumps(result),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for n in ('source','trace','output'):p.add_argument(n,type=Path)
    p.add_argument('--limb',required=True);p.add_argument('--cloth',required=True)
    a=p.parse_args();run(a.source,a.trace,a.limb,a.cloth,a.output)
