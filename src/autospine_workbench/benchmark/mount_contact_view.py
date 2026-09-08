"""ROI images show projected layers; contacts remain unreviewed."""
from html import escape
from .semantic_view import _image_url
LABELS={'boundary_pair_support':'两层边界接近', 'boundary_over_target_interior':'源边界覆盖另一层内部',
        'overlap_only':'仅有内部像素重叠','no_local_support':'局部无支持','no_source_boundary':'源层无有效边界'}


def render(doc,candidate,images):
    layers={r['layer_id']:r for r in candidate['layers']};cards=[]
    for row in doc['rows']:
        if not row['relations']:
            cards.append(f"<article><h2>{escape(row['name'])} / {escape(row['bone_id'])}</h2><p>没有可比较的对应层候选。</p></article>")
        for relation in row['relations']:
            target=layers[relation['target_layer_id']];roi=relation['roi'];picture='无有效边界'
            if roi:
                x,y,r,b=roi;parts=[]
                for layer_id in (row['layer_id'],relation['target_layer_id']):
                    layer=layers[layer_id];lx,ly,lr,lb=layer['bbox']
                    url=_image_url(images[layer_id],layer['image_sha256'])
                    parts.append(f'<image href="{url}" x="{lx}" y="{ly}" width="{lr-lx}" height="{lb-ly}" opacity=".7"/>')
                px,py=relation['boundary_point']
                picture=f'<svg viewBox="{x} {y} {r-x} {b-y}" role="img" aria-label="局部源层与对应层叠加">'+''.join(parts)+f'<circle cx="{px}" cy="{py}" r="2" fill="#e34"/></svg>'
            cards.append(f'''<article><h2>{escape(row['name'])} → {escape(target['name'])}</h2>
<p>参考骨骼：{escape(row['bone_id'])}；对应层：{escape(target['layer_id'])}</p>{picture}
<h3>{LABELS[relation['status']]}</h3><p>重叠像素：{relation['overlap_pixels']}；
源边界接近目标alpha：{relation['boundary_near_target_pixels']}；
源边界接近目标边界：{relation['boundary_pair_pixels']}</p></article>''')
    return f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'; base-uri 'none'">
<title>局部边界接触诊断</title><style>body{{font:16px/1.6 system-ui;margin:24px;color:#233548;background:#f4f6f8}}
main{{display:grid;grid-template-columns:repeat(auto-fit,minmax(350px,1fr));gap:20px}}article{{background:white;padding:16px;overflow-wrap:anywhere}}
svg{{width:100%;background:repeating-conic-gradient(#ddd 0% 25%,white 0% 50%) 0/16px 16px}}h2{{font-size:20px}}</style>
<h1>局部边界接触诊断</h1><p>两层以70%透明度叠加；红点为距骨骼参考点最近的源alpha边界像素。
局部半径{doc['parameters']['roi_radius_px']}px，边界接近范围3px（棋盘距离）。
这只是setup投影证据，不能证明真实接触、腰口或翅膀根部。对应层由候选绑定集合检索，未自动采用。</p>
<main>{''.join(cards)}</main></html>'''
