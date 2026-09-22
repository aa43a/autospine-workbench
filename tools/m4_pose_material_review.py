"""Trace source material hidden in setup, without treating it as missing artwork."""
import argparse
from copy import deepcopy
from hashlib import sha256
from html import escape
from io import BytesIO
import json
from pathlib import Path
import numpy as np
from PIL import Image
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.targets.character43.affine_pose import sample


def transfer(vertices,values,triangles,queries):
    vertices=np.asarray(vertices,float);values=np.asarray(values,float);queries=np.asarray(queries,float)
    if not all(np.isfinite(a).all() for a in (vertices,values,queries)):raise ValueError('material_nonfinite')
    output=np.full((len(queries),values.shape[1]),np.nan);hits=np.zeros(len(queries),int)
    for indices in np.asarray(triangles).reshape(-1,3):
        a,b,c=vertices[indices];matrix=np.column_stack((b-a,c-a))
        if abs(np.linalg.det(matrix))<1e-12:continue
        lo=np.min(vertices[indices],axis=0);hi=np.max(vertices[indices],axis=0)
        selected=np.where(((queries>=lo-1e-9)&(queries<=hi+1e-9)).all(axis=1))[0]
        coordinates=(queries[selected]-a)@np.linalg.inv(matrix).T
        weights=np.column_stack((1-coordinates.sum(axis=1),coordinates))
        inside=(weights>=-1e-9).all(axis=1);selected=selected[inside];weights=weights[inside]
        mapped=weights@values[indices]
        existing=hits[selected]>0
        if existing.any() and np.max(abs(output[selected[existing]]-mapped[existing]))>1e-6:
            raise ValueError('material_ambiguous_uv_or_overlap')
        output[selected]=mapped;hits[selected]+=1
    return output,hits>0


def alpha_at(texture,uv):
    # Pixel-center nearest sample for this source-material localization only.
    height,width=texture.shape;valid=np.isfinite(uv).all(axis=1)
    safe=np.where(valid[:,None],uv,0)
    x=np.floor(safe[:,0]*width).astype(int);y=np.floor(safe[:,1]*height).astype(int)
    valid &= (x>=0)&(x<width)&(y>=0)&(y<height)
    return np.where(valid,texture[np.clip(y,0,height-1),np.clip(x,0,width-1)],0)


def run(source,output,arm,body):
    receipt=json.loads((source/'report.json').read_bytes());digest=receipt['candidate_bundle_sha256']
    files=AnimatedStore(source/'isolated-store').read(digest);document=json.loads(files['skeleton.json'])
    order=[s['name'] for s in document['slots']]
    if order.index(arm)>=order.index(body):raise ValueError('material_body_not_in_front_in_setup')
    setup=deepcopy(document);setup['animations']['material-setup']={}
    vertices,_=sample(setup,'material-setup',0)
    meshes=document['skins'][0]['attachments'];a=meshes[arm][arm];b=meshes[body][body]
    names=['images/'+m.get('path',slot)+'.png' for m,slot in ((a,arm),(b,body))]
    images=[np.asarray(Image.open(BytesIO(files[name])).convert('RGBA')) for name in names]
    image,body_image=images;height,width=image.shape[:2]
    x,y=np.meshgrid(np.arange(width)+.5,np.arange(height)+.5)
    uv=np.column_stack((x.ravel()/width,y.ravel()/height))
    world,covered=transfer(np.asarray(a['uvs']).reshape(-1,2),vertices[arm],a['triangles'],uv)
    body_uv=np.full_like(world,np.nan)
    body_uv[covered],_=transfer(vertices[body],np.asarray(b['uvs']).reshape(-1,2),b['triangles'],world[covered])
    body_alpha=alpha_at(body_image[:,:,3],body_uv).reshape(height,width)
    hidden=(body_alpha>=254)&(image[:,:,3]>=8)&covered.reshape(height,width)
    output.mkdir(parents=True,exist_ok=False)
    for name,array in [('source.png',image),('body.png',body_image)]:Image.fromarray(array).save(output/name)
    marked=image.copy();marked[hidden,:3]=(255,90,60);Image.fromarray(marked).save(output/'setup-hidden.png')
    Image.fromarray((hidden*255).astype('uint8')).save(output/'setup-hidden-mask.png')
    ys,xs=np.where(hidden)
    report=dict(candidate=digest,source_identity=receipt['source_identity'],arm=arm,body=body,authority='none',selected=False,
        source_textures={n:sha256(files[n]).hexdigest() for n in names},
        setup_occluded_visible_texels=int(hidden.sum()),visible_texels=int((image[:,:,3]>=8).sum()),
        mesh_uncovered_visible_texels=int(((image[:,:,3]>=8)&~covered.reshape(height,width)).sum()),
        hidden_bounds=None if not len(xs) else [int(xs.min()),int(ys.min()),int(xs.max()+1),int(ys.max()+1)],
        scope='source_texel_center_setup_alpha_localization_not_dynamic_occlusion_or_missing_material_proof')
    (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    markup=f'''<!doctype html><meta charset="utf-8"><title>肩部姿态素材核查</title>
<style>body{{background:#17232e;color:#e8edf4;font:16px system-ui;margin:30px}}.grid{{display:flex;gap:30px}}img{{height:538px;image-rendering:auto;background:#344553}}figure{{margin:0}}p{{max-width:1000px;line-height:1.7}}</style>
<h1>肩部姿态素材核查 · {escape(arm)}</h1><p>左：原始手臂纹理。中：橙色标记在 setup 中被上衣不透明像素遮住的区域。右：原始上衣。</p>
<div class="grid"><figure><img src="source.png"><figcaption>原始纹理</figcaption></figure><figure><img src="setup-hidden.png"><figcaption>setup 遮挡范围</figcaption></figure><figure><img src="body.png"><figcaption>上衣纹理</figcaption></figure></div>
<p>被上衣遮住的可见源像素：{report['setup_occluded_visible_texels']} / {report['visible_texels']}。这表示已有图像在 setup 被遮挡，不等于缺失图像。源纹理边界在抬臂后是否自然，需要动作与连接表达验证；本页不删除像素、不修改权重或自动采用。</p><p>像素中心近邻采样，仅用于定位；不代替 Runtime 混合或动态遮挡检查。</p>'''
    (output/'index.html').write_text(markup,encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source','output'):p.add_argument(name,type=Path)
    p.add_argument('--arm',required=True);p.add_argument('--body',required=True)
    a=p.parse_args();run(a.source,a.output,a.arm,a.body)
