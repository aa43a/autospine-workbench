"""Editable root hypotheses with rigid chest-follow and local hinge preview."""
from html import escape
from hashlib import sha256
import json
from .wing_preview_parts import partition
from .semantic_view import _image_url
from .wing_root_draft import validate
from .wing_root_review_script import SCRIPT


def render(roots,candidate,images,draft):
    validate(roots,draft)
    if len(roots['rows'])!=1:raise ValueError('wing_preview_single_relation_required')
    row=roots['rows'][0];layers={r['layer_id']:r for r in candidate['layers']}
    source=layers[row['layer_id']];target=layers[row['target_layer_id']]
    parts,residual=partition(source,images[row['layer_id']],row['components'])
    def image(raw,layer):
        x,y,r,b=layer['bbox'];url=_image_url(raw,sha256(raw).hexdigest())
        return f'<image href="{url}" x="{x}" y="{y}" width="{r-x}" height="{b-y}"/>'
    wings=image(residual,source)+''.join(f'<g data-wing="{key}">{image(raw,source)}</g>' for key,raw in parts.items())
    markers=''.join(f'<circle data-root-marker="{key}" r="5" fill="#d34"/>' for key in parts)
    controls=[]
    for i,c in enumerate(row['components']):
        options='<option value="">未选择</option>'+''.join(f'<option value="{j}">候选 {j+1} · {r["source_xy"]}</option>' for j,r in enumerate(c['roots']))
        disabled='' if c['roots'] else ' disabled'
        controls.append(f'<label>C{c["component_id"]} · {c["area_pixels"]}像素 <select data-record="{i}"{disabled}>{options}</select></label>')
    state=json.dumps({'roots':roots,'draft':draft},ensure_ascii=True).replace('<','\u003c');w,h=candidate['canvas']
    return f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'; script-src 'unsafe-inline'; base-uri 'none'">
<title>翼根选择与胸骨跟随预览</title><style>body{{font:16px/1.6 system-ui;margin:24px;color:#233548;background:#f4f6f8}}
main{{display:flex;gap:24px;flex-wrap:wrap;align-items:flex-start}}svg{{width:min(800px,100%);height:auto;background:#eee}}aside{{max-width:440px;max-height:800px;overflow:auto}}label{{display:block;margin:8px 0}}button,select{{padding:8px}}</style>
<h1>翼根选择与胸骨跟随预览</h1><p>简化SVG几何预览，不是官方Spine Runtime。整个上衣层按胸骨刚性转动；
已选翼片可绕候选根部局部转动，未选组件只跟随胸骨。低alpha边缘与微小组件不做局部摆动，因此动态边缘可能不连续；未生成生产权重。上衣源层还覆盖部分翼片投影，可能出现重影；本页用于核对挂接，不是最终合成。</p>
<button id="undo">撤销选择</button> <button id="save">保存完整草稿</button><label>恢复草稿 <input id="load" type="file" accept=".json"></label>
<label>胸骨转角 <input id="chest-angle" type="range" min="-15" max="15" step="1" value="0"></label>
<label>已选翼片局部转角 <input id="flap-angle" type="range" min="-15" max="15" step="1" value="0"></label>
<label><input id="front" type="checkbox" checked>试验：翅膀在上衣前（不保存为层序决定）</label><button id="reset-pose">回到setup</button>
<p id="status" role="status"></p><main><svg viewBox="0 0 {w} {h}" role="img" aria-label="翼根与胸骨跟随预览">
<g id="stage">{image(images[row['target_layer_id']],target)}<g id="wings">{wings}{markers}</g></g></svg><aside>{''.join(controls)}</aside></main>
<script id="state" type="application/json">{state}</script><script>{SCRIPT}</script></html>'''
