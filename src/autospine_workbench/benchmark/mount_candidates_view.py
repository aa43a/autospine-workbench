"""Mount geometry in source canvas coordinates with review-only hypotheses."""
from html import escape
from .semantic_view import _image_url
LABELS = {'garment':'服装', 'prop':'物件', 'wing':'翅膀', 'conflict':'语义冲突',
 'wear.skirt':'裙装', 'wear.pants':'裤装', 'accessory.held':'手持物',
 'accessory.attached':'身体挂件', 'accessory.wing':'翅膀', 'unknown':'未知'}


def render(doc, candidate, composite, images):
    layers = {r['layer_id']:r for r in candidate['layers']}
    w,h = candidate['canvas']; source = _image_url(composite,candidate['composite_sha256']); cards=[]
    for row in doc['layers']:
        layer=layers[row['layer_id']]; x,y,r,b=layer['bbox']
        texture=_image_url(images[row['layer_id']],row['image_sha256']); marks=[]; options=[]
        for option in row['mount_options']:
            ax,ay=option['anchor_xy']; point=option['nearest_alpha_xy']; bone=escape(option['bone_id'])
            marks.append(f'<circle cx="{ax}" cy="{ay}" r="7" fill="#d34"/><text x="{ax+8}" y="{ay}" font-size="20">{bone}</text>')
            if point:
                px,py=point
                marks.append(f'<path d="M{ax} {ay}L{px} {py}" stroke="#d34" stroke-width="3"/>'
                             f'<circle cx="{px}" cy="{py}" r="5" fill="#087"/>')
            distance='无不透明像素' if point is None else f"{option['distance_px']:.2f}px / 高度{option['normalized_distance']*100:.2f}%"
            options.append(f'<li>{bone}：{distance}；'+('接近，待核对接触关系' if option['nearby'] else '缺少近距离支持')+'</li>')
        cards.append(f'''<article><h2>{escape(row['name'])} · {LABELS[row['category']]}</h2>
<svg viewBox="0 0 {w} {h}" role="img" aria-label="候选骨骼点与最近alpha像素"><image href="{source}" width="{w}" height="{h}" opacity=".12"/>
<image href="{texture}" x="{x}" y="{y}" width="{r-x}" height="{b-y}"/>{''.join(marks)}</svg>
<p>并列语义假设：{' / '.join(LABELS[v] for v in row['semantic_hypotheses'])}</p>
<ul>{''.join(options)}</ul><p>没有选择挂接点；需核对实际接触、遮挡及运动需求。</p>
<p>缺失骨骼：{escape('、'.join(row['missing_bones']) or '无')}</p></article>''')
    return f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'; base-uri 'none'">
<title>语义与挂接候选</title><style>body{{font:16px/1.6 system-ui;margin:24px;background:#f4f6f8;color:#233548}}
main{{display:grid;grid-template-columns:repeat(auto-fit,minmax(400px,1fr));gap:20px}}article{{background:white;padding:18px;border-radius:8px}}
svg{{width:100%;background:#eee}}h2{{font-size:20px}}</style><h1>语义与挂接候选 · {escape(doc['character_id'])}</h1>
<p>红点是骨骼参考点，绿点是最近alpha像素，连线仅表示距离。接近阈值为源层整体高度的5%，尚未校准。
裙／裤、手持／挂件需看图区分；翅膀根部可能被遮挡。这里没有自动拆层、创建骨链或修改绑定。</p>
<main>{''.join(cards)}</main></html>'''
