"""Texture-context visualization of sparse candidate weight samples."""
import base64
from html import escape

LABELS = {'residual_stays_unassigned': '低透明度残余保持未归属',
          'ownership_review_required': '区域尚未填写归属',
          'source_semantic_conflict': '归属语义与图层语义冲突，请复核',
          'garment_or_accessory_solver_required': '需要专用服装或饰品解算器',
          'side_conflict': '角色侧别冲突', 'semantic_chain_mismatch': '所选骨骼不符合当前语义的完整骨链',
          'disconnected_bone_chain': '骨链父子关系不连续',
          'semantic_chain_checked': '语义与骨链检查通过，仅生成采样权重'}
COLORS = [(255, 114, 128), (88, 210, 170), (94, 167, 255)]


def render(document, entries, skeleton):
    cards = []
    for layer, raw, _, _ in entries:
        rows = [r for r in document['records'] if r['layer_id'] == layer['layer_id']]
        x, y, right, bottom = layer['bbox']
        margin = 30
        svg = [f'<image x="{x}" y="{y}" width="{right-x}" height="{bottom-y}" '
               f'href="data:image/png;base64,{base64.b64encode(raw).decode()}" opacity=".6"/>']
        for row in rows:
            for sample in row['samples']:
                color = [round(sum(COLORS[i][axis]*w['weight'] for i, w in enumerate(sample['influences'])))
                         for axis in range(3)]
                title = ', '.join(f"{w['bone_id']} {w['weight']:.1%}" for w in sample['influences'])
                px, py = sample['canvas_xy']
                svg.append(f'<circle cx="{px}" cy="{py}" r="2.5" fill="rgb({color[0]},{color[1]},{color[2]})">'
                           f'<title>{escape(title)}</title></circle>')
        used = {b for row in rows for b in row['bone_ids']}
        for bone in skeleton['bones']:
            if bone['id'] not in used:
                continue
            hx, hy = bone['head_xy']; tx, ty = bone['tail_xy']
            svg.append(f'<path d="M{hx} {hy}L{tx} {ty}" stroke="#ffe373" stroke-width="2"/>'
                       f'<text x="{hx}" y="{hy}" fill="white" font-size="12">{escape(bone["id"])}</text>')
        details = ''.join(f'<li>{escape(r["component_id"])}：{escape(LABELS.get(r["reason_code"],r["reason_code"]))}'
                          f' · {len(r["samples"])} 个采样点</li>' for r in rows)
        cards.append(f'<section><h2>{escape(layer["name"])}</h2><svg viewBox="{x-margin} {y-margin} '
                     f'{right-x+2*margin} {bottom-y+2*margin}">{"".join(svg)}</svg><ul>{details}</ul></section>')
    count = sum(r['status'] == 'sampled_candidate' for r in document['records'])
    return f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>区域权重采样</title>
<style>body{{background:#101821;color:#edf3fa;font:16px system-ui;margin:24px}}a{{color:#80d8ff}}
main{{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:20px}}
section{{background:#1f2b39;padding:18px;border-radius:12px}}svg{{width:100%;height:520px;background:#343e4b}}
li{{margin:10px 0}}</style><h1>{escape(document['project_id'])} · 区域权重试算</h1>
<p>{count} 个区域产生采样候选。红／绿／蓝对应骨链第 1／2／3 根骨骼；混合色表示权重混合，悬停点查看数值。</p>
<p>本报告每区域最多 {document['sample_limit']} 个源像素中心采样，项目总预算 256 点。尚无三角网格，未验证弯曲、接缝或 Runtime，不代表正式绑定。</p>
<p><a href="index.html">返回归属草稿复核</a></p><main>{''.join(cards)}</main></html>'''
