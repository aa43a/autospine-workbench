"""Diagnostic setup mesh overlays and explicit deformation test results."""
from html import escape
from .semantic_view import _image_url


def render_mesh_candidate(candidate,report,composite,images):
    weight_label='关节平面平滑权重' if report['profile']=='joint-plane-three-bone-v2' else '三骨距离权重'
    w,h=candidate['canvas']; source=_image_url(composite,candidate['composite_sha256'])
    layers={r['layer_id']:r for r in candidate['layers']};cards=[];counts={};issues=[]
    for row in report['layers']:
        counts[row['status']]=counts.get(row['status'],0)+1
        original=layers[row['layer_id']];x,y,r,b=original['bbox']
        if not row['vertices_xy']:
            issues.append(f'<li>{escape(original["name"])}：{escape("；".join(row["reason_codes"]))}</li>')
            continue
        texture=_image_url(images[row['layer_id']],original['image_sha256'])
        lines=[]
        for tri in row['triangles']:
            points=' '.join(f'{row["vertices_xy"][i][0]},{row["vertices_xy"][i][1]}' for i in tri)
            lines.append(f'<polygon points="{points}" fill="none" stroke="#00776a" stroke-width=".7"/>')
        metrics=[];qa=row['qa']
        if qa:
            for probe in qa['probes']:
                metrics.append(f'<tr><td>{escape(probe["id"])}</td><td>{probe["inverted_triangle_count"]}</td><td>{probe["max_edge_stretch"]:.3f}</td></tr>')
        status={'blocked':'阻塞，保留诊断','candidate_requires_review':'候选待复核','reviewed_noop':'未生成'}[row['status']]
        cards.append(f'''<article><h2>{escape(original['name'])} · {status}</h2>
<p>{len(row['vertices_xy'])} 顶点 / {len(row['triangles'])} 三角形</p>
<svg viewBox="0 0 {w} {h}"><image href="{source}" width="{w}" height="{h}" opacity=".1"/>
<image href="{texture}" x="{x}" y="{y}" width="{max(1,r-x)}" height="{max(1,b-y)}"/>{''.join(lines)}</svg>
<p>{escape('；'.join(row['reason_codes']))}</p><table><thead><tr><th>测试</th><th>翻转三角形</th><th>最大边长比</th></tr></thead>
<tbody>{''.join(metrics)}</tbody></table></article>''')
    return f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'; base-uri 'none'">
<title>三骨加权网格诊断</title><style>
body{{max-width:1400px;margin:24px auto;padding:0 20px;font:16px/1.6 system-ui;color:#234;background:#f5f7fa}}
.notice{{padding:16px;background:#fff0cc}}main{{display:grid;grid-template-columns:repeat(auto-fit,minmax(390px,1fr));gap:20px}}
article{{background:white;border:1px solid #ccd;padding:16px}}svg,table{{width:100%}}td,th{{text-align:left;border-bottom:1px solid #ddd}}
</style><h1>三骨加权网格诊断</h1><p class="notice">实验profile：alpha规则网格、{weight_label}、局部坐标LBS。
尚未加入关节加密、接缝补偿或正式Spine导出。弯曲测试失败会阻塞，setup可重建不等于动画质量合格。</p>
<p>{escape(str(counts))}</p><main>{''.join(cards)}</main><details><summary>未生成网格的图层</summary><ul>{''.join(issues)}</ul></details></html>'''
