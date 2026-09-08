"""Original layers, measured components and proposed anatomical-side bindings."""
from html import escape
from ..resolved_project import canonical_sha256
from .semantic_view import _image_url

REASONS = {'semantic_ambiguous': '语义不明确：需要人工指定部件用途',
           'empty_layer': '空图层', 'hidden_layer': '隐藏图层',
           'component_split_review_required': '两个主要连通域：可复核按组件分区的候选',
           'garment_semantics_review_required': '服装候选：仅建议 setup 跟随 pelvis，需确认裙/裤语义',
           'layer_requires_split': '主要连通域并非两个，需要进一步切分分析',
           'component_side_ambiguous': '组件与左右骨链的位置关系不明确'}


def render_structure(candidate, skeleton, bindings, draft, report, composite, images):
    if report['source_bindings_sha256'] != canonical_sha256(bindings) or \
            report['source_draft_sha256'] != canonical_sha256(draft) or \
            bindings['candidate_sha256'] != canonical_sha256(candidate) or \
            bindings['source_skeleton_sha256'] != canonical_sha256(skeleton):
        raise ValueError('structure_view_source_mismatch')
    w, h = candidate['canvas']
    original = _image_url(composite, candidate['composite_sha256'])
    sources = {r['layer_id']: r for r in candidate['layers']}
    cards = []
    for row in report['layers']:
        source = sources[row['layer_id']]; x, y, r, b = source['bbox']
        texture = _image_url(images[row['layer_id']], source['image_sha256'])
        boxes, details = [], []
        for component in row['components']:
            left, top, right, bottom = component['bbox']; cx, cy = component['centroid']
            side = component.get('side'); color = {'l': '#087f8c', 'r': '#a750a0'}.get(side, '#b76700')
            boxes.append(f'<rect x="{left}" y="{top}" width="{right-left}" height="{bottom-top}" fill="none" stroke="{color}" stroke-width="3"/>'
                         f'<circle cx="{cx}" cy="{cy}" r="5" fill="{color}"/>')
            bones = ', '.join(component.get('bone_ids', [])) or '待确定'
            details.append(f'<li>组件 {component["id"]}：{component["area"]} 像素；候选骨骼 {escape(bones)}</li>')
        cards.append(f'''<article><h2>{escape(row['name'])}</h2><p>{escape(REASONS.get(row['reason_code'],row['reason_code']))}</p>
<svg viewBox="0 0 {w} {h}" aria-label="原图层及连通域边界"><image href="{original}" width="{w}" height="{h}" opacity=".12"/>
<image href="{texture}" x="{x}" y="{y}" width="{max(1,r-x)}" height="{max(1,b-y)}"/>{''.join(boxes)}</svg>
<p>共 {row['component_count']} 个连通域；未展示区域 {row['omitted_alpha_pixel_count']} 个像素，源图未删除。</p><ul>{''.join(details)}</ul></article>''')
    return f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'; base-uri 'none'">
<title>剩余图层结构候选</title><style>body{{max-width:1400px;margin:24px auto;padding:0 20px;font:16px/1.6 system-ui;background:#f5f7fa;color:#233548}}
main{{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:18px}}article{{background:white;padding:18px;border:1px solid #ccd}}svg{{width:100%}}
.notice{{background:#fff0cc;padding:16px}}h2{{font-size:21px}}</style><h1>剩余图层结构候选</h1>
<p class="notice">左右依据已复核骨架的位置关系；颜色和框只显示候选，不代表确认。小组件仍完整保留于源图。
此页不修改绑定，不切出新PNG，不生成双侧权重；裙装的 pelvis 建议仅用于刚性 setup，不代表裙摆变形已实现。</p>
<main>{''.join(cards)}</main></html>'''
