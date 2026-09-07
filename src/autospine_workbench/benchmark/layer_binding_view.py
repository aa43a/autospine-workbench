"""Layer pixels and complete rigid/mesh-chain options in PSD coordinates."""
from html import escape

from .semantic_view import _image_url
from .region_binding_view import REASONS
from .layer_binding_controls import controls, panel, SCRIPT, option_label


def render_layer_bindings(candidate, assisted, skeleton, document, composite, images, draft):
    from ..asset.joints.layer_binding import validate_layer_bindings
    from .layer_binding_draft import validate_layer_binding_draft
    validate_layer_bindings(candidate, assisted, skeleton, document)
    validate_layer_binding_draft(document, draft)
    w,h=candidate['canvas']; source=_image_url(composite,candidate['composite_sha256'])
    bones={b['id']:b for b in skeleton['bones']}; cards=[]
    reasons={**REASONS,'name_side_unreviewed':'名称左右侧尚待核对',
             'bilateral_coverage_requires_review':'可选择双侧两条骨链，需核对是否包含两侧肢体',
             'mesh_weights_required':'需要生成网格和顶点权重','coverage_review_required':'需核对图层覆盖的骨段'}
    for layer,row,record in zip(candidate['layers'],document['bindings'],draft['records']):
        texture=_image_url(images[row['layer_id']],row['image_sha256']); x,y,r,b=row['bbox']
        groups=[]
        for option in row['options']:
            lines=[]
            for index,bone_id in enumerate(option['bone_ids']):
                bone=bones[bone_id]; hx,hy=bone['head_xy'];tx,ty=bone['tail_xy']
                color=('#00897b','#e87518','#794bc4')[index%3]
                lines.append(f'<path d="M{hx} {hy}L{tx} {ty}" stroke="{color}" stroke-width="7"/>'
                             f'<circle cx="{hx}" cy="{hy}" r="8" fill="{color}"/>')
            groups.append(f'<g data-chain="{escape(option["id"],quote=True)}">'+''.join(lines)+'</g>')
        opts=''.join(f'<li>{escape(option_label(o))}</li>' for o in row['options'])
        suggested=next((option_label(o) for o in row['options'] if o['id']==row['suggested_option_id']),'待选择')
        why='；'.join(escape(reasons.get(code,code)) for code in row['reason_codes'])
        cards.append(f'''<article><h2>{escape(layer['name'])} <small>{escape(row['layer_id'])}</small></h2>
<svg viewBox="0 0 {w} {h}" role="img" aria-label="图层和候选骨链">
<image href="{source}" width="{w}" height="{h}" opacity=".12"/>
<image href="{texture}" x="{x}" y="{y}" width="{max(1,r-x)}" height="{max(1,b-y)}"/>{''.join(groups)}</svg>
<p>建议：{escape(suggested)}</p><ul>{opts}</ul><p>{why}</p>{controls(row,record)}</article>''')
    mesh=sum(any(o['mode']=='mesh_chain' for o in r['options']) for r in document['bindings'])
    return f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'; script-src 'unsafe-inline'; base-uri 'none'">
<title>单骨与多骨链绑定复核</title><style>
body{{max-width:1400px;margin:24px auto;padding:0 20px;font:16px/1.6 system-ui;color:#233548;background:#f5f7fa}}
.notice{{padding:16px;background:#fff0cc;margin-bottom:18px}}main{{display:grid;grid-template-columns:repeat(auto-fit,minmax(330px,1fr));gap:18px}}
article{{padding:16px;background:white;border:1px solid #ccd;border-radius:8px;overflow-wrap:anywhere}}
svg{{width:100%;background:repeating-conic-gradient(#eee 0% 25%,white 0% 50%) 0/20px 20px}}
h2{{font-size:20px}}small{{color:#667}}label{{display:block;margin:8px 0}}
select,textarea{{width:100%;padding:8px;box-sizing:border-box}}button{{padding:10px}}fieldset{{border:1px solid #ccd}}</style>
<h1>单骨与多骨链绑定复核</h1><p class="notice">同一图层可以选择多骨 Mesh 骨链。不同颜色表示链中不同骨段；
当前仅确定影响骨骼集合，尚未生成网格或权重。名称侧别是建议，需对照图像核对；所有草稿初始待处理。</p>
{panel(document,draft)}<p>共{len(document['bindings'])}层，其中{mesh}层具有多骨链选项。选择选项后突出显示对应骨链。</p>
<main>{''.join(cards)}</main><script>{SCRIPT}</script></html>'''
