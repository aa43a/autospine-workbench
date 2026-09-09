"""Standalone visual inspection of exact candidate masks, without decisions."""
import base64
import json
from pathlib import Path
from html import escape


def render(project, entries, draft=None, suggestions=None):
    sections = []
    for layer, raw, candidate, digest in entries:
        w = layer['bbox'][2]-layer['bbox'][0]; h = layer['bbox'][3]-layer['bbox'][1]
        shapes = []
        for i, row in enumerate(candidate['components'] + [candidate['residual']]):
            # Runs are half-open layer-local pixel rectangles, not bbox approximations.
            path = ' '.join(f'M{x} {y}h{end-x}v1h{x-end}z' for y, x, end in row['runs'])
            color = '#ffdd55' if row['id'] == 'low-alpha-residual' else f'hsl({i*137 % 360} 80% 65%)'
            shapes.append(f'<path data-component="{escape(row["id"], quote=True)}" d="{path}" fill="{color}"><title>{escape(row["id"])} · {row["pixel_count"]} px · 归属未确定</title></path>')
        image = base64.b64encode(raw).decode('ascii')
        sections.append(f'''<section data-layer="{escape(layer['layer_id'], quote=True)}"><h2>{escape(layer['name'])}</h2>
<p>{len(candidate['components'])} 个连通区域 · 低 alpha 残余 {candidate['residual']['pixel_count']} px · 可见像素 {candidate['visible_pixel_count']} px</p>
<label><input type="checkbox" checked onchange="this.closest('section').querySelector('g').style.display=this.checked?'':'none'">显示像素分区（悬停查看区域）</label>
<svg viewBox="0 0 {w} {h}" role="img" aria-label="{escape(layer['name'], quote=True)} 像素分区">
<image href="data:image/png;base64,{image}" width="{w}" height="{h}"/><g opacity=".55">{''.join(shapes)}</g></svg>
<p>状态：归属待复核。黄色为低 alpha 残余；未修改原纹理，未指定骨骼或左右。</p>
<details><summary>来源与候选</summary><p>{escape(layer['layer_id'])} · {digest}</p><a href="{digest}.json">候选 JSON</a></details></section>''')
    script = ''
    if draft:
        code = (Path(__file__).resolve().parents[4] / 'web/modules/component-ownership-review.js').read_text('utf-8').replace('export function ', 'function ')
        payload = json.dumps(draft, ensure_ascii=True).replace('<', '\\u003c')
        advice = json.dumps(suggestions, ensure_ascii=True).replace('<', '\\u003c')
        script = f'<script>(()=>{{{code}\nmountComponentOwnership(document,{payload},{advice});}})();</script>'
    return f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(project)} 像素分区候选</title><style>
body{{margin:24px;background:#101821;color:#e7eff7;font:16px system-ui}}a{{color:#7dd3fc}}
main{{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:20px}}
section{{background:#1e2a38;padding:18px;border-radius:10px;min-width:0}}svg{{display:block;width:100%;height:420px;margin:12px 0;background:#303946}}path{{shape-rendering:crispEdges}}details{{overflow-wrap:anywhere}}
button,select,input{{font:inherit;margin:6px 4px 6px 0;max-width:100%}}select{{display:block;width:100%;padding:8px}}button{{padding:8px 12px;cursor:pointer}}
main{{display:block}}.ownership-toolbar{{position:sticky;top:0;z-index:5;margin-bottom:20px}}.ownership-layout{{display:grid;grid-template-columns:minmax(0,2fr) minmax(260px,1fr);gap:24px}}.ownership-layout svg{{height:65vh}}section[hidden]{{display:none}}button:disabled{{cursor:default;opacity:.5}}@media(max-width:760px){{.ownership-layout{{display:block}}.ownership-toolbar{{position:static}}}}
</style><h1>{escape(project)} · 实际像素分区候选</h1><p>按 alpha≥8 的四连通区域分区；0&lt;alpha&lt;8 保留为未归属残余。连通不等于语义或骨骼归属。</p><main>{''.join(sections)}</main>{script}</html>'''
