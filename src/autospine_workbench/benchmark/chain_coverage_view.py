"""Show measured alpha coverage without treating coverage as pose accuracy."""
from html import escape

from .semantic_view import _image_url


def render_chain_coverage(candidate,skeleton,bindings,report,composite,images,draft):
    from ..resolved_project import canonical_sha256
    from .layer_binding_draft import validate_layer_binding_draft
    validate_layer_binding_draft(bindings,draft)
    if report['source_bindings_sha256']!=canonical_sha256(bindings):
        raise ValueError('chain_coverage_view_source_mismatch')
    w,h=candidate['canvas'];source=_image_url(composite,candidate['composite_sha256'])
    layers={r['layer_id']:r for r in candidate['layers']};bones={b['id']:b for b in skeleton['bones']}
    selected={r['layer_id']:r['option_id'] for r in draft['records']}
    cards=[]
    for layer in report['layers']:
        original=layers[layer['layer_id']];x,y,r,b=original['bbox']
        texture=_image_url(images[layer['layer_id']],original['image_sha256'])
        boxes=[];table=[];seen=set();lines=[]
        for comp in layer['components']:
            left,top,right,bottom=comp['bbox'];cx,cy=comp['centroid']
            boxes.append(f'<rect x="{left}" y="{top}" width="{right-left}" height="{bottom-top}" fill="none" stroke="#dd7500" stroke-width="2"/>'
                         f'<circle cx="{cx}" cy="{cy}" r="4" fill="#dd7500"/>')
        for option in layer['options']:
            chosen=' · 已按你的指令选择' if selected[layer['layer_id']]==option['option_id'] else ''
            table.append(f'<tr><th colspan="2">{escape(option["option_id"]+chosen)}</th></tr>')
            for metric in option['bones']:
                table.append(f'<tr><td>{escape(metric["bone_id"])}</td><td>{metric["covered_samples"]}/{metric["sample_count"]} · {metric["coverage_ratio"]:.0%}</td></tr>')
                if metric['bone_id'] in seen:continue
                seen.add(metric['bone_id']);bone=bones[metric['bone_id']]
                hx,hy=bone['head_xy'];tx,ty=bone['tail_xy']
                color='#007b6c' if metric['coverage_ratio']>=.5 else '#bf2635'
                lines.append(f'<path d="M{hx} {hy}L{tx} {ty}" stroke="{color}" stroke-width="5"/>')
        cards.append(f'''<article><h2>{escape(original['name'])}</h2><p>{layer['alpha_pixel_count']} 个alpha像素 ·
{layer['component_count']} 个4连通域（展示{len(layer['components'])}个，省略{layer['omitted_component_count']}个，
省略区域共{layer['omitted_alpha_pixel_count']}像素）</p>
<svg viewBox="0 0 {w} {h}"><image href="{source}" width="{w}" height="{h}" opacity=".12"/>
<image href="{texture}" x="{x}" y="{y}" width="{max(1,r-x)}" height="{max(1,b-y)}"/>{''.join(boxes+lines)}</svg>
<table><thead><tr><th>候选骨段</th><th>alpha覆盖样本</th></tr></thead><tbody>{''.join(table)}</tbody></table></article>''')
    return f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'; base-uri 'none'">
<title>骨链 alpha 覆盖分析</title><style>
body{{max-width:1400px;margin:24px auto;padding:0 20px;font:16px/1.6 system-ui;background:#f5f7fa;color:#233548}}
.notice{{padding:16px;background:#fff0cc}}main{{display:grid;grid-template-columns:repeat(auto-fit,minmax(390px,1fr));gap:20px}}
article{{background:white;padding:16px;border:1px solid #ccd}}svg{{width:100%}}table{{width:100%;border-collapse:collapse}}
td,th{{text-align:left;padding:4px;border-bottom:1px solid #ddd}}th{{overflow-wrap:anywhere}}</style>
<h1>骨链 alpha 覆盖分析</h1><p class="notice">alpha≥8，4连通；每段21个样本，半径3像素。
橙框为连通域，红线表示覆盖率低于50%的骨段。低覆盖只提示几何不一致，不自动否定已选绑定；
高覆盖也不证明语义、关节或权重正确。此页不生成网格，不修改你的选择。</p><main>{''.join(cards)}</main></html>'''
