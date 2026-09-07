"""Source-bound skeleton overlay with explicit review and terminal provenance."""
from html import escape
from .semantic_view import _image_url


def render_assisted_skeleton(candidate, assisted, skeleton, composite):
    from ..asset.joints.reviewed_skeleton import validate_reviewed_skeleton
    validate_reviewed_skeleton(candidate, assisted, skeleton)
    w, h = candidate['canvas']
    image = _image_url(composite, candidate['composite_sha256'])
    lines, rows = [], []
    colors = {'assisted_review': '#087d71', 'derived': '#2764b5', 'fallback': '#b06b00'}
    labels = {'assisted_review': '辅助复核坐标', 'derived': '明确推导', 'fallback': '末端延伸'}
    unit = max(w, h) / 700
    for index, bone in enumerate(skeleton['bones'], 1):
        x, y = bone['head_xy']; tx, ty = bone['tail_xy']
        kind = bone['provenance']['kind']; color = colors[kind]
        lines.append(f'<path d="M{x} {y} L{tx} {ty}" stroke="{color}" stroke-width="{3*unit}"/>'
                     f'<circle cx="{x}" cy="{y}" r="{4*unit}" fill="{color}"/>'
                     f'<text x="{x+6*unit}" y="{y-6*unit}" font-size="{12*unit}">{index}</text>')
        rows.append(f'<tr><td>{index}. {escape(bone["id"])}</td><td>{escape(bone["parent_id"] or "—")}</td>'
                    f'<td>{bone["length"]:.2f}</td><td>{labels[kind]}</td></tr>')
    reason_labels = {'all_joint_reviews_required': '标注尚未全部复核',
                     'all_joint_positions_required': '仍有缺失或不可观测关节',
                     'reviewed_central_points_preserved': '已保留中央关节点修正',
                     'terminal_points_fallback': '头、手、足末端由相邻骨段延伸',
                     'skeleton_review_required': '骨架仍为待复核候选',
                     'assisted_skeleton_torso_too_short': '躯干长度不足',
                     'assisted_skeleton_vertical_order_invalid': '中央关节点纵向顺序异常',
                     'assisted_skeleton_bone_too_short': '存在过短骨段',
                     'assisted_skeleton_geometry_invalid': '骨段越界或几何无效'}
    reasons = '；'.join(escape(reason_labels.get(reason, reason)) for reason in skeleton['reason_codes'])
    state = '已生成候选骨架' if skeleton['status'] == 'candidate_requires_review' else '当前输入阻塞'
    return f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'; base-uri 'none'">
<title>人工修正后的候选骨架</title><style>
body{{max-width:1250px;margin:24px auto;padding:0 20px;font:16px/1.6 system-ui;color:#233548;background:#f5f7fa}}
.notice{{padding:16px;background:#fff0cc}}main{{display:grid;grid-template-columns:3fr 2fr;gap:24px}}
svg{{width:100%;background:repeating-conic-gradient(#ddd 0% 25%,white 0% 50%) 0/20px 20px}}
td,th{{padding:6px;text-align:left;border-bottom:1px solid #ccd}}text{{fill:#142a40;stroke:white;stroke-width:2;paint-order:stroke}}
@media(max-width:800px){{main{{grid-template-columns:1fr}}}}</style>
<h1>人工修正后的候选骨架</h1><p class="notice">使用你已复核的辅助标注。绿色为复核坐标形成的骨段，蓝色为中间点推导，橙色为末端延伸。
这不是独立 GT、图层绑定或生产批准；原始模型观测保持不变。</p>
<p>{state} · {len(skeleton['bones'])} 根骨骼。{reasons}</p>
<main><svg viewBox="0 0 {w} {h}" role="img" aria-label="修正后骨架与角色源图">
<image href="{image}" width="{w}" height="{h}"/>{''.join(lines)}</svg>
<table><thead><tr><th>骨骼</th><th>父骨</th><th>长度 px</th><th>来源</th></tr></thead><tbody>{''.join(rows)}</tbody></table></main></html>'''
