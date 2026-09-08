"""Append diagnostic pendant bones and textures without changing existing wing motion."""
from copy import deepcopy
from hashlib import sha256
import json
import math
from PIL import Image
from .wing_spine_preview import encode
from ..asset.planning.wing_edge_ownership import decode,encode as png
from ..asset.planning.wing_pendants import analyze
from ..targets.spine43.continuous_pose import world,inspect
from ..resolved_project import canonical_sha256


def setup_frames(bones):
    frames={}
    for bone in bones:
        px,py,angle=frames.get(bone.get('parent'),(0,0,0));r=math.radians(angle)
        frames[bone['name']]=(px+bone['x']*math.cos(r)-bone['y']*math.sin(r),py+bone['x']*math.sin(r)+bone['y']*math.cos(r),angle+bone['rotation'])
    return frames


def local(x,y,frame):
    px,py,angle=frame;r=math.radians(-angle);dx,dy=x-px,y-py
    return [dx*math.cos(r)-dy*math.sin(r),dx*math.sin(r)+dy*math.cos(r)]


def build(source,files):
    if source['schema']!='autospine.wing-color-preview/v1' or source['authority']!='none' or source['production_authorized'] is not False:raise ValueError('pendant_source')
    if set(files)!=set(source['files']) or any(sha256(files[n]).hexdigest()!=d for n,d in source['files'].items()):raise ValueError('pendant_source_files')
    regions={r['id']:r for r in source['regions']};names=sorted(n for n in regions if n.startswith('wing-c'))
    images,residual,qa=analyze(files['color/unassigned.png'],regions['topwear']['setup_vertices_xy'][0],
      {n:files['editor/images/'+n+'.png'] for n in names},{n:regions[n]['setup_vertices_xy'][0] for n in names})
    before=json.loads(files['skeleton.json']);doc=deepcopy(before);frames=setup_frames(doc['bones']);atlas=files['skeleton.atlas'].decode();outputs=dict(files)
    manifest_regions=deepcopy(source['regions']);mounted=[]
    for row in qa['rows']:
        name=row['id'];outputs['pendants/'+name+'.png']=images[name]
        if row['parent'] is None:continue
        parent=row['parent']
        if parent not in frames:raise ValueError('pendant_parent_bone_missing')
        tx,ty=row['tip_xy'];lx,ly=local(tx,-ty,frames[parent]);index=len(doc['bones'])
        doc['bones'].append(dict(name=name,parent=parent,x=lx,y=ly,rotation=0));frame=(tx,-ty,frames[parent][2])
        x,y,r,b=row['bbox'];w,h=r-x,b-y;points=[[x,y],[r,y],[r,b],[x,b]];vertices=[]
        for px,py in points:vertices.extend([1,index,*local(px,-py,frame),1])
        slot=dict(name=name,bone=name,attachment=name)
        # Append within the wing group, still before topwear; existing slot order stays stable.
        target=next(i for i,s in enumerate(doc['slots']) if s['name']=='topwear');doc['slots'].insert(target,slot)
        doc['skins'][0]['attachments'][name]={name:dict(type='mesh',path=name,uvs=[0,0,1,0,1,1,0,1],triangles=[0,1,2,0,2,3],vertices=vertices,width=w,height=h)}
        animation=next(iter(doc['animations'].values()));animation['bones'][name]=dict(rotate=[dict(time=i*.5,value=v) for i,v in enumerate([0,-6,0,6,0])])
        raw=images[name];image=decode(raw);page=Image.new('RGBA',(w+4,h+4));page.paste(image,(2,2));texture='textures/'+name+'.png'
        outputs[texture]=png(page);outputs['editor/images/'+name+'.png']=raw
        atlas+=f'\n{texture}\nsize: {w+4},{h+4}\nfilter: Linear,Linear\npma: false\nrepeat: none\n{name}\nbounds: 2,2,{w},{h}\n\n'
        manifest_regions.append(dict(id=name,expected_page_uvs=[[(2+u*w)/(w+4),(2+v*h)/(h+4)] for u,v in [(0,0),(1,0),(1,1),(0,1)]],setup_vertices_xy=points,source_mesh_status='pendant_rigid_quad',review_status='candidate'))
        mounted.append(name)
    for tick in range(121):
        old,new=world(before,tick/60),world(doc,tick/60)
        if any(old[n]!=new[n] for n in old):raise ValueError('pendant_existing_motion_changed')
    geometry=inspect(doc)
    if not all(r['passed'] for r in geometry['regions'].values()):raise ValueError('pendant_geometry_failed')
    outputs['skeleton.json']=encode(doc);editor=deepcopy(doc);editor['skeleton']['images']='./images/';outputs['editor/skeleton.json']=encode(editor)
    outputs['skeleton.atlas']=atlas.encode();outputs['pendants/residual.png']=residual;outputs['pendants/candidates.json']=encode(qa)
    report=deepcopy(source);report.update(schema='autospine.wing-pendant-preview/v1',profile=qa['profile'],source_color_preview_sha256=canonical_sha256(source),
      pendant_candidates=qa,mounted_pendants=mounted,regions=manifest_regions,geometry=geometry,
      existing_attachment_motion_unchanged=True,pendant_motion='diagnostic_local_plus_minus_6deg_not_physics')
    outputs['README.txt']+=b'\nCrystal-like residual candidates attached to unique nearby wing tips with diagnostic +/-6deg local motion, not physics. Original attachment motion unchanged. Unresolved candidates and residual preserved in pendants/. No production authorization.\n'
    rows=''.join(f'<tr><td>{r["id"]}</td><td>{r["visible_pixels"]}</td><td>{r["parent"] or "blocked"}</td><td>{r["mount_candidates"][0]["distance_px"] if r["mount_candidates"] else "unknown"}</td></tr>' for r in qa['rows'])
    outputs['review.html']=f'''<!doctype html><meta charset="utf-8"><title>挂坠独立挂接候选</title><style>body{{font:18px/1.7 system-ui;margin:40px;color:#243448}}td,th{{padding:12px}}</style>
<h1>挂坠独立归属与挂接</h1><p>本轮挂接 {len(mounted)} 个候选，保留 {qa['residual_visible_pixels']} 个未归属像素。颜色与细长形状筛选是受限候选规则，不是通用语义识别。</p>
<table><tr><th>候选</th><th>像素</th><th>父翼骨</th><th>顶部到翼面距离 px</th></tr>{rows}</table>
<p><a href="preview.zip">下载 Spine 候选</a> · <a href="pendants/candidates.json">候选证据</a> · <a href="pendants/residual.png">保留残余</a></p>
<p>独立子骨骼以顶部为支点，局部±6°循环仅用于检查挂接，不是弹簧物理。原翼片、上衣、动作和层序关系保持不变；完整角色与挂接仍需复核。</p>'''.encode()
    report['files']={n:sha256(raw).hexdigest() for n,raw in outputs.items()};outputs['preview-manifest.json']=encode(report)
    return report,outputs


def verify(saved,source,files):
    if canonical_sha256(saved)!=canonical_sha256(build(source,files)[0]):raise ValueError('pendant_replay')
    return deepcopy(saved)
