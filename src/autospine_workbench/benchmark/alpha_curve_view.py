"""Review full source-image contours and projected anchor alternatives."""
from html import escape
import base64


def render(report,files):
    cards=[]
    for row in report['curves']['attachments']:
        name=row['attachment'];w,h=row['size'];paths=[]
        for curve in row['curves']:
            points=' '.join(f'{x},{y}' for x,y in curve['points'])
            color='#19b4ef' if curve['status']=='closed_contour' else '#ed9b22'
            paths.append(f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="0.6"/>')
        for anchor in row['anchors']:
            for option in anchor['options']:
                x,y=option['pixel_xy'];color='#38ed73' if anchor['status']=='candidate_anchor' else '#ff3c68'
                paths.append(f'<circle cx="{x}" cy="{y}" r="1.5" fill="{color}"/>')
        raw=base64.b64encode(files['editor/images/'+name+'.png']).decode()
        counts={s:sum(a['status']==s for a in row['anchors']) for s in sorted({a['status'] for a in row['anchors']})}
        cards.append(f'<section><h2>{escape(name)}</h2><p>{row["boundary_edges"]} 条边；{escape(str(counts))}</p>'
                     f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="完整轮廓与锚点"><image href="data:image/png;base64,{raw}" width="{w}" height="{h}"/>{"".join(paths)}</svg></section>')
    return '<!doctype html><meta charset="utf-8"><title>连续 alpha 曲线锚点</title><style>body{font:16px system-ui;background:#edf1f5;margin:24px;color:#20344b}section{display:inline-block;vertical-align:top;background:white;margin:8px;padding:20px;max-width:520px}svg{width:100%;max-height:650px;background:#ddd}p{overflow-wrap:anywhere}</style><h1>连续 alpha 曲线锚点</h1><p>蓝：完整像素边缘；橙：歧义角点；绿：唯一且可嵌入的候选锚点；红：多解或无法嵌入。尚未配对曲线、求解形状约束或采用结果。</p>'+(''.join(cards) or '<p>此角色无对应关系，不计为接缝通过。</p>')
