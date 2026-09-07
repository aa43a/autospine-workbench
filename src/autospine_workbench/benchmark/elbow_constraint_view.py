"""Same-angle auxiliary/corrected wireframes; explicitly sampled numerical QA."""
from html import escape
from ..asset.joints.elbow_constraint_report import validate_report
from ..asset.joints.elbow_constraints import prepare,solve
from ..asset.joints.elbow_alternatives import deform
from ..asset.joints.mesh_weights import _area


def render(mesh,skeleton,report):
    validate_report(mesh,skeleton,report)
    bones = {b['id']:b for b in skeleton['bones']}
    rows = {r['layer_id']:r for r in mesh['layers']}
    out = ['<!doctype html><meta charset="utf-8"><title>肘部局部约束</title><style>'
           'body{font:16px sans-serif;background:#15202b;color:#eee;margin:28px}'
           '.pair{display:grid;grid-template-columns:1fr 1fr;gap:16px}svg{width:100%;height:310px;background:#243442}'
           '</style><h1>肘部局部约束修正</h1><p>左：辅助骨；右：面积/边长约束修正。'
           '红色为面积低于 50%。固定刚性端部、保留全部三角形，每点修正量受限。'
           '通过仅指逐度数值检查，不是纹理、接缝、连续时间或 Spine Runtime 通过。</p>']
    for result in report['layers']:
        if result['status']=='not_evaluated':continue
        row = rows[result['layer_id']]
        context = prepare(row,[bones[i['bone_id']] for i in row['weights'][0]])
        out.append(f'<h2>{escape(row["layer_id"])}</h2><p>{escape(result["status"])} · 最小面积 '
                   f'{result["min_area_ratio"]:.1%} · 最大边长比 {result["max_edge_stretch"]:.3f} · '
                   f'最大修正 {result["max_correction_px"]:.2f}px</p>')
        for angle in (-90,90):
            samples = [deform(row['vertices_xy'],row['weights'],context['bones'],angle,'half_angle_auxiliary'),solve(context,angle)]
            points = sum(samples,[])
            x,y = [min(p[i] for p in points)-10 for i in (0,1)]
            w,h = [max(p[i] for p in points)-v+10 for i,v in enumerate((x,y))]
            out.append(f'<h3>{angle}°</h3><div class="pair">')
            for sample in samples:
                out.append(f'<svg viewBox="{x} {y} {w} {h}" role="img" aria-label="约束修正对照">')
                for tri,area in zip(row['triangles'],context['areas']):
                    ratio = _area(sample,tri)/area
                    color = '#ff5555' if ratio < .5 else '#ffb44a' if ratio > 2 else '#65cfab'
                    coords = ' '.join(f'{sample[i][0]},{sample[i][1]}' for i in tri)
                    out.append(f'<polygon points="{coords}" fill="{color}" fill-opacity=".35" stroke="{color}" stroke-width=".4"/>')
                out.append('</svg>')
            out.append('</div>')
    if not any(r['status']!='not_evaluated' for r in report['layers']):out.append('<p>无已选 Mesh，未评估。</p>')
    return ''.join(out)
