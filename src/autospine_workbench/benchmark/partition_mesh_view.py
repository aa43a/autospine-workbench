"""Per-region topology with actual joint names and strict raster support results."""
from html import escape
from .semantic_view import _image_url


def render_mesh(candidate,report,composite,images):
    w,h=candidate['canvas'];background=_image_url(composite,candidate['composite_sha256'])
    sources={r['layer_id']:r for r in candidate['layers']};cards=[]
    for row in report['layers']:
        source=sources[row['layer_id']];x,y,r,b=source['bbox'];qa=row['qa'];raster=row['raster_qa']
        texture=_image_url(images[row['layer_id']],row['image_sha256']);lines=[]
        for triangle in row['triangles']:
            points=' '.join(f'{row["vertices_xy"][i][0]},{row["vertices_xy"][i][1]}' for i in triangle)
            lines.append(f'<polygon points="{points}" fill="none" stroke="#087f8c" stroke-width=".8"/>')
        rows=[]
        if qa:
            for probe in qa['probes']:
                rows.append(f'<tr><td>{escape(probe["id"])}</td><td>{probe["inversions"]}</td><td>{probe["min_area_ratio"]:.3f}</td><td>{probe["max_edge_stretch"]:.3f}</td></tr>')
        summary=f'未覆盖alpha像素：{raster["uncovered_alpha_pixels"]}' if raster else '尚未生成网格'
        cards.append(f'''<article><h2>{escape(source['name'])} · {'阻塞' if row['status']=='blocked' else '候选待复核'}</h2>
<p>影响骨骼：{escape(', '.join(row['bone_ids']))}；{len(row['vertices_xy'])} 顶点，{len(row['triangles'])} 三角形。</p>
<svg viewBox="0 0 {w} {h}"><image href="{background}" width="{w}" height="{h}" opacity=".12"/>
<image href="{texture}" x="{x}" y="{y}" width="{r-x}" height="{b-y}"/>{''.join(lines)}</svg>
<p>{summary}；{escape(', '.join(row['reason_codes']))}</p><details><summary>逐关节弯曲QA</summary><table><tr><th>骨骼/角度</th><th>翻转</th><th>最小面积比</th><th>最大边长比</th></tr>{''.join(rows)}</table></details></article>''')
    return f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'; base-uri 'none'">
<title>分区多区域权重实验</title><style>body{{max-width:1400px;margin:24px auto;padding:0 20px;font:16px/1.6 system-ui;background:#f5f7fa;color:#233548}}
main{{display:grid;grid-template-columns:repeat(auto-fit,minmax(360px,1fr));gap:18px}}article{{padding:18px;background:white;border:1px solid #ccd}}svg{{width:100%}}
table{{width:100%;font-size:13px}}.notice{{padding:16px;background:#fff0cc}}</style><h1>分区多区域权重实验</h1>
<p class="notice">左右区域独立网格，仅使用对应侧骨链；鞋使用单脚骨刚性权重。全部残余沿用原分区保留，不采用4px试算。
QA包含每个关节±15/30/60/90度、面积与拉伸；alpha像素未被网格覆盖会阻塞。不是正式绑定、接缝或Runtime验收。</p><main>{''.join(cards)}</main></html>'''
