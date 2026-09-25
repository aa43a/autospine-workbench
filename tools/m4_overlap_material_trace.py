"""Trace setup-hidden source texels through a frozen overlap; no seam constraint."""
import argparse
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import numpy as np
from PIL import Image
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.targets.character43.affine_pose import sample
from m4_pose_material_review import transfer, alpha_at


def coverage(body_vertices, mesh, texture, points):
    uv, hit = transfer(body_vertices, np.asarray(mesh['uvs']).reshape(-1, 2),
                       mesh['triangles'], points)
    values = alpha_at(texture, uv)
    return values, hit


def run(source, frontier, output):
    digest = json.loads((source/'report.json').read_bytes())['candidate_bundle_sha256']
    row = next(r for r in json.loads(frontier.read_bytes())['records'] if r['character']=='alice')
    if digest != row['artifact_sha256']:
        raise ValueError('overlap_identity_mismatch')
    files = AnimatedStore(source/'isolated-store').read(digest)
    if any(sha256(files[name]).hexdigest()!=value for name,value in row['textures'].items()):
        raise ValueError('overlap_texture_changed')
    doc = json.loads(files['skeleton.json']); animation='external-motion'
    arm, body = row['arm'], row['body']; motion=doc['animations'][animation]
    order=[s['name'] for s in doc['slots']]
    if order.index(arm)>=order.index(body) or motion.get('drawOrder'):
        raise ValueError('overlap_order_not_static_covered')
    if motion.get('slots'):
        raise ValueError('overlap_slot_animation_requires_active_sampling')
    slots={s['name']:s for s in doc['slots']}
    if any(slots[s].get('color','ffffffff')!='ffffffff' or
           slots[s].get('blend','normal')!='normal' for s in (arm,body)):
        raise ValueError('overlap_tint_or_blend_unsupported')
    meshes=doc['skins'][0]['attachments']; a=meshes[arm][arm]; b=meshes[body][body]
    texture=lambda m,s:np.asarray(Image.open(BytesIO(files['images/'+m.get('path',s)+'.png'])).convert('RGBA'))[:,:,3]
    arm_alpha, body_alpha=texture(a,arm),texture(b,body)
    setup,bones=sample(dict(doc,animations={'setup':{}}),'setup',0)
    y,x=np.mgrid[:arm_alpha.shape[0],:arm_alpha.shape[1]]
    uv=np.column_stack(((x.ravel()+.5)/arm_alpha.shape[1],(y.ravel()+.5)/arm_alpha.shape[0]))
    world,valid=transfer(np.asarray(a['uvs']).reshape(-1,2),setup[arm],a['triangles'],uv)
    alpha=np.zeros(len(world)); alpha[valid]=coverage(setup[body],b,body_alpha,world[valid])[0]
    root=np.asarray(bones['upperarm_r'][:2]); radius=row['radius_px']
    chosen=valid & (arm_alpha.ravel()>=8) & (alpha>=254) & (np.linalg.norm(world-root,axis=1)<=radius)
    seed_uv=uv[chosen]; ids=np.flatnonzero(chosen)
    frames=[]
    for time in (0., .7, 1.05, 1.725, 2.4, 4.):
        posed=sample(doc,animation,time)[0]
        points,found=transfer(np.asarray(a['uvs']).reshape(-1,2),posed[arm],a['triangles'],seed_uv)
        if not found.all():raise ValueError('overlap_material_correspondence_missing')
        values,hits=coverage(posed[body],b,body_alpha,points)
        frames.append(dict(time=time,fully_covered=int((values>=254).sum()),
            partially_covered=int(((values>0)&(values<254)).sum()),uncovered=int((values==0).sum()),
            outside_reference_mesh=int((~hits).sum()),
            records=[dict(source_texel=int(i),uv=u.tolist(),world=p.tolist(),
                reference_alpha=int(v),reference_mesh_covered=bool(h))
                for i,u,p,v,h in zip(ids,seed_uv,points,values,hits)]))
    report=dict(profile='setup_hidden_material_overlap_trace-v1',artifact_sha256=digest,
        textures=row['textures'],arm=arm,body=body,source_texels=len(ids),radius_px=radius,
        intent='covering_relative_motion_confirmed_by_user',frames=frames,
        selected=False,authority='none',visual_status='not_evaluated',
        scope='six_pose_nearest_texel_alpha_trace_not_framebuffer_crack_or_connection_acceptance')
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf8') as stream:
        json.dump(report,stream,ensure_ascii=False,allow_nan=False)
    print(json.dumps({**{k:v for k,v in report.items() if k!='frames'},
        'frames':[{k:v for k,v in f.items() if k!='records'} for f in frames]},ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('source','frontier','output'):parser.add_argument(name,type=Path)
    args=parser.parse_args();run(args.source,args.frontier,args.output)
