"""Combined selected-layer scene with optional unbound source reference."""
import json
from pathlib import Path
from .semantic_view import _image_url
from ..asset.joints.elbow_bake import replay,validate_bake
from ..resolved_project import canonical_sha256


def render_scene(candidate,skeleton,mesh,bake,doc,scope,images,composite):
    validate_bake(mesh,skeleton,bake)
    if canonical_sha256(bake)!=scope['source_bake_sha256']:raise ValueError('character_scene_source_mismatch')
    if canonical_sha256(doc)!=scope['skeleton_json_sha256'] or canonical_sha256(candidate)!=skeleton['candidate_sha256']:
        raise ValueError('character_scene_source_mismatch')
    originals={r['layer_id']:r for r in candidate['layers']};rows={r['layer_id']:r for r in mesh['layers']}
    baked={r['layer_id']:r for r in bake['layers']};bones={b['id']:b for b in skeleton['bones']}
    attachments=doc['skins'][0]['attachments'];cards=[]
    for slot in doc['slots']:
        name=slot['name'];original=originals[name];x,y,r,b=original['bbox'];attachment=attachments[name][name]
        if attachment['type']=='mesh':
            row=rows[name];chain=[bones[w['bone_id']] for w in row['weights'][0]]
            poses=[replay(row,chain,f,f,0) for f in baked[name]['frames']]
            source=[[p[0]-x,p[1]-y] for p in row['vertices_xy']];triangles=row['triangles']
        else:
            # This scene profile admits only fixed head/neck/chest regions in this elbow loop.
            if slot['bone'] not in ('head','neck','chest'):raise ValueError('character_scene_rigid_motion_unsupported')
            poses=[[[x,y],[r,y],[r,b],[x,b]]]*61
            source=[[0,0],[r-x,0],[r-x,b-y],[0,b-y]];triangles=[[0,1,2],[0,2,3]]
        cards.append({'name':name,'image':_image_url(images[name],original['image_sha256']),
                      'source':source,'poses':poses,'triangles':triangles,'bounds':[0,0,*candidate['canvas']]})
    data=json.dumps(cards,ensure_ascii=False).replace('<','\\u003c')
    source=_image_url(composite,candidate['composite_sha256'])
    script=Path(__file__).with_name('elbow_bake_webgl.js').read_text('utf-8')
    script+='''
const cards=JSON.parse(document.getElementById('data').textContent),frame=document.getElementById('frame');let play=false,last=0;
for(const c of cards){c.canvas=document.createElement('canvas');c.canvas.width=680;c.canvas.height=600;document.getElementById('scene').append(c.canvas);c.img=new Image();c.img.onload=()=>{c.render=textureRenderer(c.canvas,c.img);draw();};c.img.src=c.image;}
function draw(){document.getElementById('position').textContent=frame.value;for(const c of cards)if(c.render)c.render(c,c.poses[Number(frame.value)],false);}
frame.oninput=draw;document.getElementById('play').onclick=()=>{play=!play;last=0;document.getElementById('play').textContent=play?'暂停':'播放';};
document.getElementById('reference').onchange=e=>document.getElementById('source').style.opacity=e.target.checked?.25:0;
function tick(t){if(play){if(!last)last=t;let n=Math.floor((t-last)*30/1000);if(n){frame.value=(Number(frame.value)+n)%60;last+=n*1000/30;draw();}}requestAnimationFrame(tick);}requestAnimationFrame(tick);
'''
    w,h=candidate['canvas'];scale=min(660/w,580/h);left=(680-w*scale)/2;top=(600-h*scale)/2
    return f'''<!doctype html><meta charset="utf-8"><title>角色组合诊断</title><style>
body{{background:#15202b;color:#eee;font:16px system-ui;margin:24px}}#scene{{position:relative;width:680px;height:600px;background:#30404e}}canvas{{position:absolute;inset:0}}#source{{position:absolute;left:{left}px;top:{top}px;width:{w*scale}px;height:{h*scale}px;opacity:0}}pre{{white-space:pre-wrap}}</style>
<h1>已确认绑定 · 角色组合</h1><p>包含 {len(cards)} 层，另有 {len(scope['excluded_layers'])} 层未进入场景。图层顺序沿用源数据，未通过 Draw Order 复核。</p>
<button id="play">播放</button><input id="frame" type="range" min="0" max="60" value="15"><output id="position">15</output>
<label><input type="checkbox" id="reference">显示未绑定原图参考（不参与动画）</label>
<div id="scene"><img id="source" src="{source}"></div><p>接触锚点为自动候选；采样距离不是完整接缝通过。不是官方 Runtime。</p>
<script id="data" type="application/json">{data}</script><script>{script}</script>'''
