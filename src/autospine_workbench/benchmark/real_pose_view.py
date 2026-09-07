"""Read-only model observation versus constrained-candidate comparison."""
from html import escape
import math

from ..asset.joints.optimizer import BONES, JOINTS
from ..png_rgba import decode_rgba_png
from ..pose_observations import PoseObservationSet
from ..resolved_project import canonical_sha256
from .semantic_view import _image_url


def _require(condition):
    if not condition:
        raise ValueError("benchmark_real_pose_view_input_invalid")


def _point(value, canvas):
    _require(type(value) in (list, tuple) and len(value) == 2 and all(
        type(v) in (int, float) and 0 <= v <= bound and math.isfinite(v)
        for v, bound in zip(value, canvas)))
    return list(value)


def _svg(url, points, canvas, title):
    width, height = canvas
    scale = max(canvas) / 600
    lines = []
    for a, b in BONES:
        if a in points and b in points:
            p, q = points[a], points[b]
            lines.append(f'<line x1="{p[0]}" y1="{p[1]}" x2="{q[0]}" y2="{q[1]}"/>')
    marks = []
    for index, joint in enumerate(JOINTS):
        if joint not in points:
            continue
        x, y = points[joint]
        marks.append(f'<circle cx="{x}" cy="{y}" r="{4*scale}"><title>{escape(joint)}</title></circle>'
                     f'<text x="{x+6*scale}" y="{y-6*scale}" font-size="{13*scale}">{index+1}</text>')
    return f'''<svg viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title, quote=True)}">
<image href="{url}" width="{width}" height="{height}"/>
<g stroke="#00afcb" stroke-width="{2*scale}">{''.join(lines)}</g>
<g fill="#c83212" stroke="white" stroke-width="{.5*scale}">{''.join(marks)}</g></svg>'''


def render_real_pose(candidate, pose: PoseObservationSet, optimized: dict, composite: bytes) -> str:
    """Caller replays optimizer's match closure; this verifies view identity/bounds."""
    _require(type(candidate) is dict and candidate.get("schema") == "autospine.benchmark-semantic-candidates/v1"
             and candidate.get("authority") == "none" and isinstance(pose, PoseObservationSet))
    canvas = candidate.get("canvas")
    _require(type(canvas) is list and len(canvas) == 2
             and all(type(v) is int and 0 < v <= 4096 for v in canvas))
    _require(pose.project_id == candidate.get("character_id")
             and pose.image_sha256 == candidate.get("composite_sha256")
             and list(pose.canvas_size) == canvas and pose.document is not None
             and canonical_sha256(pose.document) == pose.document_sha256)
    _require(type(optimized) is dict and optimized.get("schema") == "autospine.joint-optimization/v1"
             and optimized.get("authority") == "none" and optimized.get("diagnostic_only") is True
             and optimized.get("candidate_sha256") == canonical_sha256(candidate)
             and optimized.get("pose_sha256") == pose.document_sha256
             and optimized.get("status") in ("blocked", "candidate_requires_review"))
    url = _image_url(composite, pose.image_sha256)
    image = decode_rgba_png(composite)
    _require((image.width, image.height) == tuple(canvas))
    original = {}
    for joint in JOINTS:
        row = pose.joints.get(joint)
        if row is None:
            continue
        _require(type(row.detector_score) in (int, float) and 0 <= row.detector_score <= 1
                 and math.isfinite(row.detector_score))
        _require(row.visibility in ("visible", "occluded", "out_of_frame", "unknown"))
        original[joint] = _point((row.x, row.y), canvas)
    records = optimized.get("joints")
    _require(type(records) is list)
    adjusted = {}
    if optimized["status"] == "blocked":
        _require(not records)
    else:
        _require(len(records) == len(JOINTS))
        for joint, row in zip(JOINTS, records):
            _require(type(row) is dict and row.get("joint_id") == joint)
            adjusted[joint] = _point(row.get("position"), canvas)
    reasons = optimized.get("reason_codes")
    _require(type(reasons) is list and all(type(v) is str for v in reasons))
    status = "优化被阻塞：不展示虚构的优化关节" if optimized['status'] == 'blocked' else '优化候选：仍需复核'
    rows = []
    visibility = {"visible": "可见", "occluded": "遮挡", "out_of_frame": "画外", "unknown": "未知"}
    for index, joint in enumerate(JOINTS):
        row = pose.joints.get(joint)
        score = f'{row.detector_score:.4f}' if row else '未提供'
        visible = visibility[row.visibility] if row else '未提供'
        before = ', '.join(f'{v:.3f}' for v in original[joint]) if joint in original else '未提供'
        after = ', '.join(f'{v:.3f}' for v in adjusted[joint]) if joint in adjusted else '未提供'
        rows.append(f'<tr><td>{index+1}. {escape(joint)}</td><td>{score}</td><td>{visible}</td>'
                    f'<td>{before}</td><td>{after}</td></tr>')
    raw_svg = _svg(url, original, canvas, '原始模型观测')
    final_svg = _svg(url, adjusted, canvas, '优化后的候选')
    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'; script-src 'none'; connect-src 'none'; base-uri 'none'; form-action 'none'">
<title>姿态观测与优化候选对照</title><style>
body{{font:16px/1.6 system-ui;margin:24px auto;max-width:1200px;padding:0 20px;color:#172b3a;background:#f5f6f8}}
.notice{{background:#fff1d3;padding:16px}}.panels{{display:grid;grid-template-columns:1fr 1fr;gap:20px}}
svg{{width:100%;background:white;background-image:conic-gradient(#ddd 25%,transparent 0 50%,#ddd 0 75%,transparent 0);background-size:20px 20px}}
table{{border-collapse:collapse;width:100%;background:white}}td,th{{padding:8px;border:1px solid #ccc;text-align:left}}.table{{overflow:auto}}
code{{overflow-wrap:anywhere}}@media(max-width:700px){{.panels{{grid-template-columns:1fr}}}}
</style></head><body><h1>姿态观测与优化候选对照</h1>
<p class="notice">模型输出不是人工真值。尚无人工标注，不能计算关节误差。检测器分数不是经过校准的正确率。
左右表示角色自身；连线仅辅助检查。此页只读，不产生批准决定。
DWPose 的规范分数使用 s/(1+s) 编码；原始 SimCC 分数另行封存，不可直接套用旧阈值。</p>
<p>检测器：{escape(str(pose.detector_id))} · 版本：{escape(str(pose.detector_version))}</p>
<p><strong>{status}</strong></p><p>诊断：<code>{escape('；'.join(reasons))}</code></p>
<main class="panels"><section><h2>原始模型观测</h2>{raw_svg}</section>
<section><h2>优化后的候选</h2>{final_svg}</section></main>
<div class="table"><table><thead><tr><th>关节编号</th><th>规范观测分数</th><th>可见性</th><th>原始 PSD 坐标</th><th>优化 PSD 坐标</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div></body></html>'''
