"""Fixed-angle wireframes are diagnostic geometry, not texture playback."""
from html import escape
from .semantic_view import _image_url


def render_corrective(candidate,composite,report):
    w,h=candidate['canvas'];source=_image_url(composite,candidate['composite_sha256']);cards=[]
    for row in report['layers']:
        groups=[];metrics=[]
        for index,sample in enumerate(row['samples']):
            lines=[]
            for key,color in (('baseline_positions','#dc513d'),('positions','#087f8c')):
                for tri in row['triangles']:
                    points=' '.join(f'{sample[key][i][0]},{sample[key][i][1]}' for i in tri)
                    lines.append(f'<polygon points="{points}" fill="none" stroke="{color}" stroke-width="1"/>')
            groups.append(f'<g data-frame="{index}" style="display:{"inline" if index==4 else "none"}">{"".join(lines)}</g>')
            q=sample['qa'];metrics.append(f'<tr><td>{sample["angle"]}°</td><td>{q["inversions"]}</td><td>{q["min_area_ratio"]:.3f}</td><td>{q["max_edge_stretch"]:.3f}</td></tr>')
        cards.append(f'''<article><h2>{escape(row['layer_id'])} · {escape(row['joint_id'])}</h2><p>{'数值候选待复核' if row['status']=='candidate_requires_review' else '仍阻塞'}；
可修正顶点 {row['free_vertex_count']}；相对半角基底位移预算 {row['projection_budget_px']:.2f}px。</p>
<label>角度 <output>0°</output><input type="range" min="0" max="8" value="4" step="1"></label>
<svg viewBox="0 0 {w} {h}"><image href="{source}" width="{w}" height="{h}" opacity=".12"/>{''.join(groups)}</svg>
<details><summary>数值结果</summary><table><tr><th>角度</th><th>翻转</th><th>最小面积比</th><th>最大边长比</th></tr>{''.join(metrics)}</table></details></article>''')
    return f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'; script-src 'unsafe-inline'; base-uri 'none'">
<title>踝腕局部corrective对照</title><style>body{{max-width:1400px;margin:24px auto;padding:0 20px;font:16px/1.6 system-ui;background:#f5f7fa;color:#233548}}
main{{display:grid;grid-template-columns:repeat(auto-fit,minmax(380px,1fr));gap:20px}}article{{background:white;padding:18px;border:1px solid #ccd}}svg,input{{width:100%}}.notice{{background:#fff0cc;padding:16px}}</style>
<h1>踝／腕局部 corrective 对照</h1><p class="notice">红线是原LBS，青线是修正后网格。淡色角色只是setup参照，不是纹理动画。
本页仅旋转远端关节，48次投影保留刚性顶点和位移预算；不代表组合动作、接缝或Runtime通过。未采用到正式绑定。</p><main>{''.join(cards)}</main>
<script>const angles=[-90,-60,-30,-15,0,15,30,60,90];document.querySelectorAll('article').forEach(card=>{{card.querySelector('input').oninput=e=>{{const i=Number(e.target.value);card.querySelector('output').textContent=angles[i]+'°';card.querySelectorAll('[data-frame]').forEach(g=>g.style.display=Number(g.dataset.frame)===i?'inline':'none');}};}});</script></html>'''
