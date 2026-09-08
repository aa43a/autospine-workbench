"""Pure diagnostic Spine export from exact wing-root choices; no release authority."""
from copy import deepcopy
from hashlib import sha256
from io import BytesIO
import json
from PIL import Image
from .wing_root_draft import validate
from .wing_preview_parts import partition
from ..asset.joints.partition_pixels import png
from ..resolved_project import canonical_sha256
from ..targets.spine43.continuous_pose import inspect


def encode(doc):
    return json.dumps(doc,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def verify_report(saved,roots,candidate,images,draft):
    expected,_=build(roots,candidate,images,draft)
    if canonical_sha256(saved)!=canonical_sha256(expected):raise ValueError('wing_preview_replay_mismatch')
    return deepcopy(saved)


def build(roots,candidate,images,draft):
    draft=validate(roots,draft)
    if len(roots['rows'])!=1:raise ValueError('wing_preview_single_relation_required')
    row=roots['rows'][0];layers={r['layer_id']:r for r in candidate['layers']}
    source=layers[row['layer_id']];target=layers[row['target_layer_id']]
    parts,residual=partition(source,images[row['layer_id']],row['components'])
    if sha256(images[row['target_layer_id']]).hexdigest()!=target['image_sha256']:
        raise ValueError('wing_target_image_changed')
    ax,ay=row['anchor_xy'];bones=[dict(name='root',x=0,y=0,rotation=0),
      dict(name='chest',parent='root',x=ax,y=-ay,rotation=0)]
    tracks={};selected=[];attachments={};slots=[];regions=[];files={};atlas=''
    def track(amplitude):
        return dict(rotate=[dict(time=i*.5,value=v) for i,v in enumerate([0,-amplitude,0,amplitude,0])])
    tracks['chest']=track(10)
    def attach(name,raw,layer,index,pivot):
        nonlocal atlas
        x,y,r,b=layer['bbox'];w,h=r-x,b-y;points=[[x,y],[r,y],[r,b],[x,b]]
        vertices=[]
        for px,py in points:vertices.extend([1,index,px-pivot[0],-(py-pivot[1]),1])
        attachments[name]={name:dict(type='mesh',path=name,uvs=[0,0,1,0,1,1,0,1],
          triangles=[0,1,2,0,2,3],vertices=vertices,width=w,height=h)}
        slots.append(dict(name=name,bone=bones[index]['name'],attachment=name))
        with Image.open(BytesIO(raw)) as image:
            if image.size!=(w,h):raise ValueError('wing_image_dimensions')
            page=Image.new('RGBA',(w+4,h+4));page.paste(image.convert('RGBA'),(2,2))
            texture='textures/'+name+'.png';files[texture]=png('RGBA',page.size,page.tobytes())
        files['editor/images/'+name+'.png']=raw
        atlas+=f'\n{texture}\nsize: {w+4},{h+4}\nfilter: Linear,Linear\npma: false\nrepeat: none\n{name}\nbounds: 2,2,{w},{h}\n\n'
        regions.append(dict(id=name,setup_vertices_xy=points,
          expected_page_uvs=[[(2+u*w)/(w+4),(2+v*h)/(h+4)] for u,v in [(0,0),(1,0),(1,1),(0,1)]],
          review_status='diagnostic_only',source_mesh_status='rigid_component_quad'))
    attach('topwear',images[row['target_layer_id']],target,1,[ax,ay])
    attach('wing-residual',residual,source,1,[ax,ay])
    choices={r['component_id']:r['root_index'] for r in draft['records']}
    for component in row['components']:
        key=component['component_id']
        if key not in parts:continue
        index=1;pivot=[ax,ay];choice=choices[key]
        if choice is not None:
            pivot=component['roots'][choice]['source_xy'];name='wing-c'+str(key);index=len(bones)
            bones.append(dict(name=name,parent='chest',x=pivot[0]-ax,y=ay-pivot[1],rotation=0))
            tracks[name]=track(12);selected.append(dict(component_id=key,root_index=choice,source_xy=pivot))
        attach('wing-c'+str(key),parts[key],source,index,pivot)
    doc=dict(skeleton=dict(spine='4.3.26',images='./editor/images/'),bones=bones,slots=slots,
      skins=[dict(name='default',attachments=attachments)],animations={'wing-root-inspection':dict(bones=tracks)})
    geometry=inspect(doc)
    if not all(r['passed'] for r in geometry['regions'].values()):raise ValueError('wing_geometry_failed')
    files['skeleton.json']=encode(doc);editor=deepcopy(doc);editor['skeleton']['images']='./images/'
    files['editor/skeleton.json']=encode(editor);files['skeleton.atlas']=atlas.encode();files['draft.json']=encode(draft)
    report=dict(schema='autospine.wing-spine-preview/v1',profile='selected-wing-hinges-v1',
      source_roots_sha256=canonical_sha256(roots),source_draft_sha256=canonical_sha256(draft),
      selected_roots=selected,regions=regions,geometry=geometry,status='needs_review',
      authority='none',production_authorized=False,full_character_animation=False,
      limitations=['topwear_wing_projection_ghosting','residual_follows_chest_only','draw_order_unreviewed',
                   'diagnostic_rigid_hinges_not_secondary_motion'])
    files['README.txt']=('Spine 4.3.26 diagnostic subset. Import editor/skeleton.json with editor/images.\n'
      'User-selected roots only; no production authorization. Topwear ghosting, residual edges and draw order remain unreviewed.\n').encode()
    choices_html=''.join(f'<li>C{r["component_id"]}：候选 {r["root_index"]+1}，根部 ({r["source_xy"][0]:g}, {r["source_xy"][1]:g})</li>' for r in selected)
    files['review.html']=f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<title>琪露诺翼根 Spine 局部预览</title><style>body{{font:18px/1.7 system-ui;max-width:900px;margin:40px auto;padding:20px;background:#f4f6f8;color:#243448}}</style>
<h1>已选翼根 → Spine 局部预览</h1><ul>{choices_html}</ul>
<p>导出目标 Spine 4.3.26；胸骨 ±10°，翼片局部 ±12°，两秒循环。</p>
<p><a href="preview.zip">下载预览包</a> · <a href="draft.json">已导入草稿</a> · <a href="preview-manifest.json">来源与数值报告</a></p>
<p>解压后导入 editor/skeleton.json，保留 images 目录。</p>
<p>这是上衣与翅膀的局部诊断包。上衣中的翼片重影、仅跟随胸骨的残余边缘与层序仍待处理；没有生产授权。</p>
<p>官方 Runtime 检查结果保存在上级目录 official-runtime-report.json；数值通过不等于视觉问题已解决。</p></html>'''.encode()
    report['files']={n:sha256(raw).hexdigest() for n,raw in files.items()}
    files['preview-manifest.json']=encode(report)
    return report,files
