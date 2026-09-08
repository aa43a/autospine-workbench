"""Residual footprint and alpha contribution, with reversible policy controls."""
from html import escape
from io import BytesIO
import hashlib
import json
from .semantic_view import _image_url
from .residual_draft import validate_draft
from .residual_controls import SCRIPT


def render_review(candidate,composite,partitions,draft,previews):
    from PIL import Image
    from ..asset.joints.partition_pixels import png
    validate_draft(partitions,draft)
    sources={r['layer_id']:r for r in candidate['layers']};w,h=candidate['canvas']
    background=_image_url(composite,candidate['composite_sha256']);cards=[]
    for layer_id,before,after,qa in previews:
        source=sources[layer_id];x,y,r,b=source['bbox'];panels=[]
        for label,raw,metric in (('保留原残余',before,qa['before']),('4px邻近补全试算',after,qa['after'])):
            with Image.open(BytesIO(raw)) as image:
                colors=bytes(v for a in image.getchannel('A').tobytes() for v in ((220,35,55,210) if a else (0,0,0,0)))
                overlay=png('RGBA',image.size,colors)
            url=_image_url(overlay,hashlib.sha256(overlay).hexdigest())
            panels.append(f'<section><h3>{label}</h3><p>{metric["visible_pixels"]} 像素；占源图 alpha 总量 {metric["alpha_mass_ratio"]:.3%}</p>'
                f'<svg viewBox="0 0 {w} {h}"><image href="{background}" width="{w}" height="{h}" opacity=".15"/>'
                f'<image href="{url}" x="{x}" y="{y}" width="{r-x}" height="{b-y}"/></svg></section>')
        cards.append(f'<article><h2>{escape(source["name"])}</h2><p>试算可移动 {qa["moved_pixels"]} 个低alpha像素，RGBA重建通过。</p><div class="panels">{"".join(panels)}</div>'
                     '<label>本层选择<select><option value="pending">待复核</option><option value="retain">保留全部残余</option><option value="nearest_4px">采用4px邻近规则作为草稿</option></select></label>'
                     '<label>复核说明<textarea maxlength="2000"></textarea></label></article>')
    state=json.dumps(draft,ensure_ascii=True).replace('<','\\u003c')
    return f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'; script-src 'unsafe-inline'; base-uri 'none'">
<title>分区残余归属复核</title><style>body{{max-width:1200px;margin:24px auto;padding:0 20px;font:16px/1.6 system-ui;background:#f5f7fa;color:#233548}}
article{{padding:18px;background:white;border:1px solid #ccd;margin:20px 0}}.panels{{display:flex;flex-wrap:wrap}}section{{flex:1;min-width:280px}}svg{{width:100%}}
.notice{{padding:16px;background:#fff0cc}}select,textarea{{display:block;width:100%;padding:8px;box-sizing:border-box}}button{{padding:10px}}label{{display:block;margin:10px 0}}</style>
<h1>分区残余归属复核</h1><p class="notice">红色仅高亮残余位置，不是源像素颜色。4px试算只处理alpha 1–7且距已分配高alpha像素不超过4步的点；
四连通距离可跨透明背景，等距、远处与高alpha残余保持未定。像素无损不证明归属正确；右侧为候选，默认不采用。</p>
<button id="save">保存整份草稿</button> <button id="undo">撤销上一步</button><label>恢复草稿<input id="load" type="file" accept=".json"></label><p id="status" role="status"></p>
{''.join(cards)}<script id="draft" type="application/json">{state}</script><script>{SCRIPT}</script></html>'''
