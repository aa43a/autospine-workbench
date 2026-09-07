"""Spatial area-loss visualization without pretending to render textures."""
from html import escape
from ..asset.joints.mesh_weights import _area, _deform, _frames
from ..asset.joints.mesh_area import validate_area_report


def render_area(mesh, skeleton, report):
    validate_area_report(mesh, skeleton, report)
    bones = {b['id']: b for b in skeleton['bones']}
    rows = {r['layer_id']: r for r in mesh['layers']}
    parts = ['<!doctype html><meta charset="utf-8"><title>Mesh 面积检查</title>',
             '<style>body{font:16px sans-serif;background:#15202b;color:#eee;margin:32px}'
             'svg{width:46%;height:440px;background:#243442;margin:1%}section{margin:32px 0}</style>',
             '<h1>Mesh 面积检查 · 实验阈值</h1><p>每 1° 扫描肘部 −90° 至 +90°。'
             '红色：面积低于 50%；橙色：超过 200%；绿色：范围内。左为 setup，右为最小面积时刻。'
             '显示线框，不是纹理或 Runtime 证据；不删除透明三角形。接缝尚未评估，不产生发布权。</p>']
    for result in report['layers']:
        if result['status'] == 'not_evaluated':
            continue
        row = rows[result['layer_id']]
        chain = [bones[i['bone_id']] for i in row['weights'][0]]
        angle = result['worst']['angle_degrees']
        setup = row['vertices_xy']
        moved = _deform(row['weights'], _frames(chain, angle))
        ratios = [_area(moved,t)/_area(setup,t) for t in row['triangles']]
        all_points = setup + moved
        x,y = [min(p[i] for p in all_points)-10 for i in (0,1)]
        w,h = [max(p[i] for p in all_points)-v+10 for i,v in enumerate((x,y))]
        parts.append(f'<section><h2>{escape(row["layer_id"])}</h2><p>{escape(result["status"])} · '
                     f'最小面积 {result["min_area_ratio"]:.1%} · {angle}° · '
                     f'三角形 {result["worst"]["triangle_index"]}</p>')
        for points in (setup, moved):
            parts.append(f'<svg viewBox="{x} {y} {w} {h}" role="img" aria-label="面积变化线框">')
            for index, (triangle, ratio) in enumerate(zip(row['triangles'], ratios)):
                color = '#ff5555' if ratio < .5 else '#ffb44a' if ratio > 2 else '#65cfab'
                coords = ' '.join(f'{points[i][0]},{points[i][1]}' for i in triangle)
                parts.append(f'<polygon points="{coords}" fill="{color}" fill-opacity=".35" '
                             f'stroke="{color}" stroke-width=".4"><title>{index}: {ratio:.4f}</title></polygon>')
            parts.append('</svg>')
        parts.append('</section>')
    if not any(r['status'] != 'not_evaluated' for r in report['layers']):
        parts.append('<p>没有可评估的加权 Mesh；不表示通过。</p>')
    return ''.join(parts)
