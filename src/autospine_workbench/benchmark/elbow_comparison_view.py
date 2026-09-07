"""Same-angle wireframe comparisons with explicit experimental QA outcomes."""
from html import escape
from ..asset.joints.elbow_comparison import validate_comparison
from ..asset.joints.elbow_alternatives import deform
from ..asset.joints.mesh_weights import _area


def render_comparison(mesh,skeleton,doc):
    validate_comparison(mesh,skeleton,doc)
    bones = {b['id']:b for b in skeleton['bones']}
    rows = {r['layer_id']:r for r in mesh['layers']}
    names = {'lbs':'原 LBS','half_angle_auxiliary':'半角辅助骨','rotation_corrective':'旋转保持修正'}
    out = ['<!doctype html><meta charset="utf-8"><title>肘部变形对照</title><style>',
           'body{font:16px sans-serif;background:#15202b;color:#eee;margin:28px}'
           '.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}'
           'svg{width:100%;height:330px;background:#243442}section{margin:32px 0}'
           '@media(max-width:750px){.grid{grid-template-columns:1fr}}</style>',
           '<h1>肘部变形对照</h1><p>同一网格与关节，逐 1° 检查 −90° 至 +90°。'
           '红色：面积低于 50%；橙色：面积超过 200%。阈值未经基准校准，未自动采用任何方案。'
           '此页是线框诊断；未完成纹理、接缝或官方 Runtime 验证。</p>']
    for result in doc['layers']:
        if not result['methods']: continue
        row = rows[result['layer_id']]
        chain = [bones[i['bone_id']] for i in row['weights'][0]]
        out.append(f'<section><h2>{escape(row["layer_id"])}</h2><div class="grid">')
        for method in result['methods']:
            out.append(f'<div><h3>{names[method["mode"]]}</h3><p>{escape(method["status"])} · '
                       f'最小面积 {method["min_area_ratio"]:.1%}<br>最大边长比 {method["max_edge_stretch"]:.3f}'
                       f' · 翻转 {method["inverted_triangle_samples"]}</p></div>')
        out.append('</div>')
        for angle in (-90,90):
            samples = [deform(row['vertices_xy'],row['weights'],chain,angle,m['mode']) for m in result['methods']]
            points = [p for sample in samples for p in sample]
            x,y = [min(p[i] for p in points)-10 for i in (0,1)]
            w,h = [max(p[i] for p in points)-v+10 for i,v in enumerate((x,y))]
            out.append(f'<h3>{angle}°</h3><div class="grid">')
            for sample in samples:
                out.append(f'<svg viewBox="{x} {y} {w} {h}" role="img" aria-label="同角度变形">')
                for t in row['triangles']:
                    ratio = _area(sample,t)/_area(row['vertices_xy'],t)
                    color = '#ff5555' if ratio < .5 else '#ffb44a' if ratio > 2 else '#65cfab'
                    coords = ' '.join(f'{sample[i][0]},{sample[i][1]}' for i in t)
                    out.append(f'<polygon points="{coords}" fill="{color}" fill-opacity=".35" stroke="{color}" stroke-width=".4"/>')
                out.append('</svg>')
            out.append('</div>')
        out.append('</section>')
    if not any(r['methods'] for r in doc['layers']): out.append('<p>没有已选加权 Mesh，未作比较。</p>')
    return ''.join(out)
