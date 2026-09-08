"""Full-source context for previous outer matches and inward wing hypotheses."""
from html import escape
from .semantic_view import _image_url


def render(doc,candidate,images):
    layers={r['layer_id']:r for r in candidate['layers']};w,h=candidate['canvas'];cards=[]
    for row in doc['rows']:
        parts=[];items=[]
        for layer_id in (row['target_layer_id'],row['layer_id']):
            layer=layers[layer_id];x,y,r,b=layer['bbox'];url=_image_url(images[layer_id],layer['image_sha256'])
            parts.append(f'<image href="{url}" x="{x}" y="{y}" width="{r-x}" height="{b-y}" opacity=".65"/>')
        for x,y in row['previous_points']:parts.append(f'<circle cx="{x}" cy="{y}" r="9" fill="none" stroke="#e90" stroke-width="4"/>')
        ax,ay=row['anchor_xy'];parts.append(f'<circle cx="{ax}" cy="{ay}" r="7" fill="#158"/>')
        for component in row['components']:
            for root in component['roots']:
                x,y=root['source_xy'];cid=component['component_id']
                parts.append(f'<path d="M{x} {y}L{ax} {ay}" stroke="#c34" stroke-width="2"/>'
                             f'<circle cx="{x}" cy="{y}" r="6" fill="#c34"/><text x="{x+8}" y="{y}" font-size="20">C{cid}</text>')
            details='；'.join(f"到躯干参考点{r['anchor_distance_px']:.1f}px，连线目标alpha命中{r['target_corridor_samples']}/33" for r in component['roots']) or '保留组件，未生成根部'
            items.append(f"<li>C{component['component_id']}：面积{component['area_pixels']}px，投影被目标alpha覆盖{component['projected_target_coverage']*100:.1f}%；{details}</li>")
        cards.append(f'''<section><h2>{escape(row['name'])} → {escape(layers[row['target_layer_id']]['name'])}</h2>
<svg viewBox="0 0 {w} {h}" role="img" aria-label="橙色旧外轮廓点与红色内侧根部候选">{''.join(parts)}</svg>
<ul>{''.join(items)}</ul></section>''')
    return f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'; base-uri 'none'">
<title>翅膀内侧根部候选</title><style>body{{font:16px/1.6 system-ui;margin:24px;color:#233548;background:#f4f6f8}}
section{{background:white;padding:20px;margin:20px 0}}svg{{width:min(100%,800px);background:#eee}}li{{margin:8px 0}}</style>
<h1>翅膀内侧根部候选</h1><p>橙圈：旧外轮廓匹配。红点：各连通域朝躯干的近端候选。蓝点：躯干参考点。
层图以65%透明度叠加，投影覆盖不是已验证的遮挡，未确认前后顺序或隐藏根部，未自动采用。</p>
{''.join(cards) or '<p>没有翅膀对应关系。</p>'}</html>'''
