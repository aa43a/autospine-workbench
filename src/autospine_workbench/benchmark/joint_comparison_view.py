"""Read-only candidate/reference overlay, with explicit missing observations."""
from html import escape
from io import BytesIO
import hashlib

from .semantic_view import _image_url


def composite_height(candidate, raw):
    """Nonzero-alpha extent of the exact composite, not a reviewed body height."""
    from PIL import Image

    if hashlib.sha256(raw).hexdigest() != candidate['composite_sha256']:
        raise ValueError('benchmark_joint_composite_mismatch')
    with Image.open(BytesIO(raw)) as image:
        if image.format != 'PNG' or list(image.size) != candidate['canvas']:
            raise ValueError('benchmark_joint_composite_mismatch')
        if 'A' not in image.getbands() and 'transparency' not in image.info:
            return None
        bbox = image.convert('RGBA').getchannel('A').getbbox()
    return bbox[3] - bbox[1] if bbox else None


def render_joint_comparison(candidate, baseline, draft, report, composite):
    from .joint_comparison import validate_joint_comparison

    validate_joint_comparison(candidate, baseline, draft, report,
                              character_height=composite_height(candidate, composite))
    width, height = candidate['canvas']
    radius = max(width, height) / 180
    marks, rows = [], []
    names = {'unmarked': '未标注', 'unobservable': '不可观测', 'observed': '已录入草稿'}
    for index, row in enumerate(report['records'], 1):
        x, y = row['candidate_position']
        marks.append(f'<g class="baseline"><circle cx="{x}" cy="{y}" r="{radius}"/>'
                     f'<text x="{x + radius}" y="{y - radius}">{index}</text></g>')
        reference = row['reference_position']
        if reference is not None:
            rx, ry = reference
            marks.append(f'<g class="reference"><path d="M{x} {y} L{rx} {ry}"/>'
                         f'<circle cx="{rx}" cy="{ry}" r="{radius}"/></g>')
        distance = '—' if row['distance_px'] is None else f"{row['distance_px']:.3f}"
        ratio = '—' if row['distance_height_ratio'] is None else f"{100 * row['distance_height_ratio']:.2f}%"
        rows.append(f'<tr><td>{index}. {escape(row["joint_id"])}</td>'
                    f'<td>{names[row["reference_status"]]}</td><td>{distance}</td><td>{ratio}</td></tr>')
    summary = report['summary']
    median = summary['median_distance_px']
    value = '暂无可比较标注' if median is None else f'{median:.3f} px'
    image = _image_url(composite, candidate['composite_sha256'])
    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>关节基线对照</title><style>
body{{font:16px/1.6 system-ui;background:#f5f6f8;color:#182333;max-width:1240px;margin:24px auto;padding:0 18px}}
.notice{{background:#fff2d0;padding:14px}}main{{display:grid;grid-template-columns:3fr 2fr;gap:24px}}
svg{{width:100%;height:auto;background:repeating-conic-gradient(#ddd 0% 25%,white 0% 50%) 0/20px 20px}}
.baseline{{fill:#ae3400;stroke:white;stroke-width:1}}text{{font:18px system-ui;paint-order:stroke;stroke-width:3}}
.reference{{fill:#087b69;stroke:#087b69;stroke-width:2}}table{{border-collapse:collapse;width:100%;font-size:14px}}
td,th{{padding:7px;border-bottom:1px solid #ccc;text-align:left}}input{{margin:8px}}
#base:not(:checked)~main .baseline{{display:none}}#ref:not(:checked)~main .reference{{display:none}}
@media(max-width:800px){{main{{grid-template-columns:1fr}}}}
</style></head><body><h1>关节基线对照</h1>
<p class="notice">橙色是旧 bbox 算法猜点，包含 fallback；左右侧尚未复核。绿色是人工草稿，仍未经正式复核。
本页只做诊断，不生成骨架、不采用候选、不作为精度验收。</p>
<p>可比较 {summary['compared']} / 17；未标注 {summary['unmarked']}；不可观测 {summary['unobservable']}。
距离中位数：{value}。</p>
<input id="base" type="checkbox" checked><label for="base">显示算法基线</label>
<input id="ref" type="checkbox" checked><label for="ref">显示草稿与偏差线</label>
<main><div><svg viewBox="0 0 {width} {height}" role="img" aria-label="PSD 合成图与关节点对照">
<image href="{image}" width="{width}" height="{height}"/>{''.join(marks)}</svg></div>
<div><table><thead><tr><th>关节</th><th>草稿状态</th><th>距离 px</th><th>高度比</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table><p>高度比分母是合成图非零 alpha 的垂直范围，含头饰等素材，
不是已复核人体高度。无 alpha 范围或无标注时为缺失值，不按零计算。</p>
<p>请在独立关节录入页记录观察，下载草稿后重新生成本对照页。基线不会填入人工草稿。</p></div></main></body></html>'''
