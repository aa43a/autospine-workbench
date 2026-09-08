"""Apply reversible texture ownership to an exact wing preview, preserving rig/motion."""
from copy import deepcopy
from hashlib import sha256
import json
from PIL import Image
from .wing_spine_preview import encode
from ..resolved_project import canonical_sha256
from ..asset.planning.wing_edge_ownership import refine,decode,encode as png


def overlap_queue(base,files):
    target=decode(files['editor/images/topwear.png']);regions={r['id']:r for r in base['regions']}
    tx,ty=regions['topwear']['setup_vertices_xy'][0];queue=[]
    for key in sorted(r for r in regions if r.startswith('wing-c')):
        image=decode(files['editor/images/'+key+'.png']);x,y=regions[key]['setup_vertices_xy'][0]
        count=exact=0;error=0;xs=[];ys=[]
        for py in range(image.height):
            for px in range(image.width):
                a=image.getpixel((px,py));u,v=px+x-tx,py+y-ty
                if a[3]<8 or not (0<=u<target.width and 0<=v<target.height):continue
                b=target.getpixel((u,v))
                if b[3]<8:continue
                count+=1;exact+=a==b;error+=sum(abs(a[i]-b[i]) for i in range(3));xs.append(px+x);ys.append(py+y)
        if count:queue.append(dict(component=key,overlap_pixels=count,exact_rgba_pixels=exact,
          rgb_mae=round(error/(3*count),6),canvas_bbox=[min(xs),min(ys),max(xs)+1,max(ys)+1],
          reason_code='source_layer_requires_semantic_split',status='needs_review',automatic_removal=False))
    return queue


def build(base,source_files):
    if base['schema']!='autospine.wing-spine-preview/v1' or base['profile']!='selected-wing-hinges-v1':
        raise ValueError('wing_edge_source_profile')
    if base['production_authorized'] is not False or base['authority']!='none':raise ValueError('wing_edge_authority')
    if set(source_files)!=set(base['files']) or any(sha256(source_files[n]).hexdigest()!=digest for n,digest in base['files'].items()):
        raise ValueError('wing_edge_source_files')
    names=sorted(r['id'] for r in base['regions'] if r['id'].startswith('wing-c'))
    parts={name:source_files['editor/images/'+name+'.png'] for name in names}
    selected={'wing-c'+str(r['component_id']) for r in base['selected_roots']}
    outputs,residual,edge=refine(parts,source_files['editor/images/wing-residual.png'],selected)
    outputs['wing-residual']=residual;files=dict(source_files)
    for name,raw in outputs.items():
        image=decode(raw);w,h=image.size;page=Image.new('RGBA',(w+4,h+4));page.paste(image,(2,2))
        files['editor/images/'+name+'.png']=raw;files['textures/'+name+'.png']=png(page)
    queue=overlap_queue(base,source_files)
    detail=encode(edge);summary={k:v for k,v in edge.items() if k!='changes'}
    summary.update(changes_file='edge-ownership.json',changes_sha256=sha256(detail).hexdigest())
    report=deepcopy(base);report.update(schema='autospine.wing-edge-preview/v1',profile=edge['profile'],
      source_preview_sha256=canonical_sha256(base),edge_ownership=summary,review_queue=queue,
      rig_and_motion_unchanged=True,target_texture_unchanged=True)
    report['limitations']=[r for r in base['limitations'] if r!='residual_follows_chest_only']+['unresolved_residual_follows_chest_only']
    files['edge-ownership.json']=detail
    files['README.txt']+=b'\nUnique nearby alpha 1..7 edge pixels now follow selected wings. Original rig, tracks and topwear preserved. Remaining edges and ghosting need review.\n'
    rows=''.join(f'<tr><td>{r["component"]}</td><td>{r["overlap_pixels"]}</td><td>{r["exact_rgba_pixels"]}</td><td>{r["rgb_mae"]}</td></tr>' for r in queue)
    files['review.html']=f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>翼片边缘与源层拆分</title>
<style>body{{font:18px/1.7 system-ui;max-width:950px;margin:40px auto;padding:20px;color:#243448;background:#f4f6f8}}td,th{{padding:10px;border-bottom:1px solid #ccc}}</style>
<h1>翼片边缘归属候选</h1><p>{edge['counts']['transferred']} 个低透明度像素改为跟随唯一邻近翼片。setup 可见 RGBA 精确不变，骨骼与动作不变。</p>
<p><a href="preview.zip">下载 Spine 包</a> · <a href="edge-ownership.json">逐像素归属与未处理原因</a> · <a href="preview-manifest.json">完整报告</a></p>
<h2>上衣重叠区域：需要源层语义拆分</h2><table><tr><th>翼片</th><th>重叠像素</th><th>RGBA 完全一致</th><th>RGB 平均差</th></tr>{rows}</table>
<p>重叠不是重复素材的证明。本候选未删除上衣像素，重影仍未解决。未能唯一归属的边缘和微小组件继续跟随胸骨。</p>
<p>仅为 Spine 4.3.26 局部诊断候选，没有生产授权。导入 editor/skeleton.json 并保留 images 目录。</p></html>'''.encode()
    report['files']={n:sha256(raw).hexdigest() for n,raw in files.items()}
    files['preview-manifest.json']=encode(report)
    return report,files


def verify(saved,base,files):
    expected,_=build(base,files)
    if canonical_sha256(saved)!=canonical_sha256(expected):raise ValueError('wing_edge_replay_mismatch')
    return deepcopy(saved)
