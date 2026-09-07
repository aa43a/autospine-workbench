"""Offline, stepped 30 fps textured preview; numerical QA separately samples 120 Hz."""
import json
from pathlib import Path
from ..asset.joints.elbow_bake import validate_bake,replay
from .semantic_view import _image_url
from ..resolved_project import canonical_sha256


def render(mesh,skeleton,doc,candidate,images):
    validate_bake(mesh,skeleton,doc)
    if canonical_sha256(candidate)!=skeleton['candidate_sha256']:raise ValueError('elbow_bake_texture_source_mismatch')
    rows={r['layer_id']:r for r in mesh['layers']}
    originals={r['layer_id']:r for r in candidate['layers']}
    bones={b['id']:b for b in skeleton['bones']}
    cards=[]
    for layer in doc['layers']:
        if not layer['frames']:continue
        row=rows[layer['layer_id']];original=originals[layer['layer_id']]
        chain=[bones[w['bone_id']] for w in row['weights'][0]]
        poses=[replay(row,chain,f,f,0) for f in layer['frames']]
        x,y=original['bbox'][:2]
        cards.append({'name':original['name'],'status':layer['status'],'qa':layer['qa'],
                      'image':_image_url(images[layer['layer_id']],original['image_sha256']),
                      'source':[[p[0]-x,p[1]-y] for p in row['vertices_xy']],
                      'triangles':row['triangles'],'poses':poses})
    data=json.dumps(cards,ensure_ascii=False,allow_nan=False).replace('<','\\u003c')
    script=Path(__file__).with_name('elbow_bake_webgl.js').read_text('utf-8')+'\n'+Path(__file__).with_name('elbow_bake_player.js').read_text('utf-8')
    return '''<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Corrective 动画预览</title><style>
body{font:16px system-ui;background:#15202b;color:#eee;margin:24px}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(360px,1fr));gap:20px}
canvas{width:100%;background:repeating-conic-gradient(#30404e 0% 25%,#263643 0% 50%) 0/24px 24px}button,input{margin:8px}article{min-width:0}</style>
<h1>Corrective 动画 · 30 FPS</h1><p>两秒测试循环：0° → +90° → 0° → −90° → 0°。播放封存关键帧的原图纹理预览。
数值 QA 另按 120Hz 检查局部偏移插值；画布以 30FPS 逐帧播放，不是 Spine Runtime。
只显示已选手臂图层，跨图层接缝与完整角色尚未验证。</p>
<button id="play">播放</button><label>帧 <input id="frame" type="range" min="0" max="60" value="15"><output id="position">15</output></label>
<label><input id="wire" type="checkbox">网格</label><main id="cards"></main>
<script type="application/json" id="data">'''+data+'</script><script>'+script+'</script>'
