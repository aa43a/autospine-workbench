"""Read-only canonical skeleton visualization, explicitly outside production."""
from html import escape

from .semantic_view import _image_url


def render_r2a(candidate, optimized, skeleton, report, composite):
    from ..asset.joints.skeleton import validate_canonical_skeleton

    validate_canonical_skeleton(candidate, optimized, skeleton)
    w, h = candidate['canvas']
    image = _image_url(composite, candidate['composite_sha256'])
    lines, rows = [], []
    for index, bone in enumerate(skeleton['bones'], 1):
        x, y = bone['head_xy']
        tx, ty = bone['tail_xy']
        kind = bone['provenance']['kind']
        color = '#0c7366' if kind == 'optimized' else '#b66b00'
        lines.append(f'<path d="M{x} {y} L{tx} {ty}" stroke="{color}" stroke-width="3"/>'
                     f'<circle cx="{x}" cy="{y}" r="4" fill="{color}"/>'
                     f'<text x="{x+5}" y="{y-5}" font-size="14">{index}</text>')
        rows.append(f'<tr><td>{index}. {escape(bone["id"])}</td><td>{escape(bone["parent_id"] or "—")}</td>'
                    f'<td>{bone["length"]:.2f}</td><td>{escape(kind)}</td></tr>')
    reasons = '；'.join(escape(v) for v in skeleton['reason_codes'])
    state = '技术链已生成候选骨架' if skeleton['status'] == 'candidate_requires_review' else '当前输入阻塞'
    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>R2-A 骨架候选</title><style>
body{{max-width:1200px;margin:24px auto;padding:0 18px;font:16px/1.6 system-ui;color:#203047;background:#f5f6f8}}
.notice{{padding:14px;background:#fff1ce}}main{{display:grid;grid-template-columns:3fr 2fr;gap:20px}}
svg{{width:100%;background:repeating-conic-gradient(#ddd 0% 25%,white 0% 50%) 0/20px 20px}}
td,th{{text-align:left;padding:6px;border-bottom:1px solid #ccd}}text{{fill:#182333;stroke:white;stroke-width:2;paint-order:stroke}}
@media(max-width:800px){{main{{grid-template-columns:1fr}}}}</style></head><body><h1>R2-A 骨架候选</h1>
<p class="notice">技术验证，不是生产批准。绿色骨段来自优化关节；橙色骨段含推导或 fallback。
未评估真实角色关节精度，也未执行 Spine Runtime 验证。</p>
<p>{state}；骨骼数 {report['bone_count']}。{reasons}</p>
<main><svg viewBox="0 0 {w} {h}" role="img" aria-label="候选骨架与源图">
<image href="{image}" width="{w}" height="{h}"/>{''.join(lines)}</svg><table><thead><tr>
<th>骨骼</th><th>父骨</th><th>长度</th><th>来源</th></tr></thead><tbody>{''.join(rows)}</tbody></table></main></body></html>'''
