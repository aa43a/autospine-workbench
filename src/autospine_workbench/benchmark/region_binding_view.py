"""Offline per-layer source overlays and candidate bone options."""
from html import escape

from .semantic_view import _image_url

REASONS = {'skeleton_blocked': '上游骨架尚未可用', 'empty_layer': '空图层',
           'hidden_layer': '隐藏图层需确认是否纳入', 'layer_outside_canvas': '图层超出画布',
           'semantic_binding_unsupported': '语义未知或当前不支持绑定',
           'semantic_roles_unreviewed': '名称语义尚未复核',
           'region_binding_requires_review': '绑定建议待复核',
           'character_side_requires_review': '角色左右侧尚未确认'}


def render_region_bindings(candidate, assisted, skeleton, document, composite, images):
    from ..asset.joints.region_binding import validate_region_bindings
    validate_region_bindings(candidate, assisted, skeleton, document)
    w, h = candidate['canvas']
    source = _image_url(composite, candidate['composite_sha256'])
    bones = {b['id']: b for b in skeleton['bones']}
    layers = {l['layer_id']: l for l in candidate['layers']}
    cards = []
    for row in document['bindings']:
        layer = layers[row['layer_id']]
        texture = _image_url(images[row['layer_id']], row['image_sha256'])
        x, y, right, bottom = row['bbox']
        overlay, options = [], []
        for option in row['bone_options']:
            bone = bones[option['bone_id']]
            hx, hy = bone['head_xy']; tx, ty = bone['tail_xy']
            overlay.append(f'<path d="M{hx} {hy}L{tx} {ty}" stroke="#00796b" stroke-width="6"/>'
                           f'<circle cx="{hx}" cy="{hy}" r="8" fill="#00796b"/>')
            local = option['setup_local']
            options.append(f'<li>{escape(option["bone_id"])}：局部中心 '
                           f'({local["x"]:.2f}, {local["y"]:.2f})，旋转 {local["rotation_degrees"]:.2f}°</li>')
        status = '待复核建议' if row['bone_options'] else '当前无法绑定'
        choice = escape(row['suggested_bone_id'] or '无唯一建议')
        reasons = '；'.join(escape(REASONS.get(r, r)) for r in row['reason_codes'])
        cards.append(f'''<article><h2>{escape(layer['name'])} <small>{escape(row['layer_id'])}</small></h2>
<svg viewBox="0 0 {w} {h}" role="img" aria-label="图层位置与骨段选项">
<image href="{source}" width="{w}" height="{h}" opacity=".12"/>
<image href="{texture}" x="{x}" y="{y}" width="{max(1,right-x)}" height="{max(1,bottom-y)}"/>
{''.join(overlay)}</svg><p>{status} · {choice}</p><ul>{''.join(options)}</ul><p>{reasons}</p></article>''')
    count = sum(bool(r['bone_options']) for r in document['bindings'])
    return f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'; base-uri 'none'">
<title>图层绑定候选</title><style>
body{{max-width:1400px;margin:24px auto;padding:0 20px;font:16px/1.6 system-ui;color:#233548;background:#f5f7fa}}
.notice{{padding:16px;background:#fff0cc}}main{{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:20px}}
article{{background:white;border:1px solid #cbd5e1;border-radius:8px;padding:16px;overflow-wrap:anywhere}}
svg{{width:100%;max-height:420px;background:repeating-conic-gradient(#eee 0% 25%,white 0% 50%) 0/20px 20px}}
h2{{font-size:19px}}small{{color:#667085}}li{{font-size:14px}}</style>
<h1>图层绑定候选</h1><p class="notice">基于已修正骨架和原始图层。名称语义仍需复核，左右未确认时同时展示两个选项。
局部变换保持原图层位置；当前页面只展示建议，不写入采用决定或导出生产 Rig。</p>
<p>共 {len(document['bindings'])} 层，{count} 层有绑定选项，{len(document['bindings'])-count} 层暂不能绑定。
按源图层记录顺序展示；淡色人物仅用于位置参照。</p><main>{''.join(cards)}</main></html>'''
