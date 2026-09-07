"""Read-only, embedded raster evidence for unassigned contact hypotheses."""
from html import escape
import math

from ..resolved_project import canonical_sha256
from .semantic_view import _image_url

RELATIONS = {"torso_arm": "肩部接触假设", "pelvis_leg": "髋部接触假设", "leg_foot": "踝部接触假设"}
REASONS = {
    "semantic_roles_unreviewed": "原图层名称仅用于配对，身体语义尚未复核",
    "character_sides_unreviewed": "角色自身左右侧未知",
    "joint_assignment_blocked": "接触区域不能直接赋为关节",
    "missing_reference_layer": "缺少参考图层",
    "missing_child_layer": "缺少配对图层",
    "empty_layer_skipped": "已跳过空图层",
    "layer_outside_canvas_skipped": "已跳过超出画布的图层",
    "disconnected_contact": "接触区域不连通",
    "low_area": "接触面积偏小",
    "high_variance": "接触范围分散",
    "gap_contact": "存在间隙，属于近接触假设",
    "CONTACT_OVERLAP_BELOW_THRESHOLD": "重叠面积低于最小接触阈值",
    "CONTACT_MASK_EMPTY": "配对图层透明区域为空",
    "CONTACT_GAP_TOO_LARGE": "间隙超过探测范围",
}


def _n(value):
    if type(value) not in (int, float) or not -1e9 <= value <= 1e9 or not math.isfinite(value):
        raise ValueError("benchmark_contact_view_geometry_invalid")
    return format(value, ".6g")


def _reasons(values):
    return "；".join(escape(REASONS.get(code, "未识别的诊断项：" + str(code))) for code in values) or "无额外诊断项"


def _point(point):
    if type(point) is not list or len(point) != 2:
        raise ValueError("benchmark_contact_view_geometry_invalid")
    return _n(point[0]), _n(point[1])


def _overlay(candidate, pair, layers, urls):
    width, height = map(_n, candidate["canvas"])
    parts = [f'<svg class="checker" viewBox="0 0 {width} {height}" role="img" aria-label="配对图层与接触位置">']
    for layer_id, color in zip(pair["layer_ids"], ("#008fa8", "#b72c99")):
        layer = layers[layer_id]
        x, y, right, bottom = layer["bbox"]
        w, h = right - x, bottom - y
        parts.append(f'<image href="{urls[layer_id]}" x="{_n(x)}" y="{_n(y)}" width="{_n(w)}" height="{_n(h)}" opacity="0.65"/>')
        parts.append(f'<rect x="{_n(x)}" y="{_n(y)}" width="{_n(w)}" height="{_n(h)}" fill="{color}" fill-opacity="0.06" stroke="{color}" vector-effect="non-scaling-stroke"/>')
    for contact in pair["contacts"]:
        bbox = contact["bbox_xywh"]
        if bbox is not None:
            if type(bbox) is not list or len(bbox) != 4:
                raise ValueError("benchmark_contact_view_geometry_invalid")
            x, y, w, h = map(_n, bbox)
            parts.append(f'<rect class="contact-bbox" x="{x}" y="{y}" width="{w}" height="{h}" fill="#e89b00" fill-opacity="0.2" stroke="#a66300" vector-effect="non-scaling-stroke"/>')
        point = contact["representative_xy"]
        if point is not None:
            x, y = _point(point)
            radius = _n(max(candidate["canvas"]) / 160)
            parts.append(f'<circle class="contact-point" cx="{x}" cy="{y}" r="{radius}" fill="#df382c" stroke="white" vector-effect="non-scaling-stroke"/>')
    return "".join(parts) + "</svg>"


def _metrics(contact):
    gap = "不适用" if contact["gap_distance_px"] is None else _n(contact["gap_distance_px"]) + " px"
    ratios = contact["overlap_ratios"]
    if type(ratios) is not list or len(ratios) != 2:
        raise ValueError("benchmark_contact_view_geometry_invalid")
    ratio_text = " / ".join(_n(value) for value in ratios)
    mode = {"overlap": "重叠", "gap": "近接触"}.get(contact["mode"], "接触模式：" + str(contact["mode"]))
    return (f'<li>{escape(mode)}：面积 {_n(contact["area"])} px²；间隙 {gap}；重叠比例 {ratio_text}。'
            f'<br>诊断：{_reasons(contact["flags"])}</li>')


def render_contact_probe(candidate, probe, composite, images):
    """Caller replays probe against source images; view additionally binds bytes."""
    if type(probe) is not dict or probe.get("schema") != "autospine.benchmark-contact-probe/v1" \
            or probe.get("authority") != "none" or probe.get("candidate_sha256") != canonical_sha256(candidate):
        raise ValueError("benchmark_contact_view_probe_mismatch")
    if candidate.get("authority") != "none":
        raise ValueError("benchmark_contact_view_candidate_invalid")
    layers = {row["layer_id"]: row for row in candidate["layers"]}
    if set(images) != set(layers):
        raise ValueError("benchmark_contact_view_images_invalid")
    urls = {}
    for layer_id, layer in layers.items():
        raw = images[layer_id]
        if type(raw) is not bytes or len(raw) != layer["image"]["byte_size"]:
            raise ValueError("benchmark_contact_view_image_changed")
        urls[layer_id] = _image_url(raw, layer["image_sha256"])
    composite_url = _image_url(composite, candidate["composite_sha256"])
    sections = []
    for relation in probe["relations"]:
        title = RELATIONS.get(relation["relation"])
        if title is None:
            raise ValueError("benchmark_contact_view_relation_invalid")
        cards = []
        for pair in relation["pairs"]:
            ids = pair["layer_ids"]
            if type(ids) is not list or len(ids) != 2 or any(layer_id not in layers for layer_id in ids):
                raise ValueError("benchmark_contact_view_layers_invalid")
            names = " ↔ ".join(escape(layers[layer_id]["name"]) for layer_id in ids)
            contacts = "<ul>" + "".join(_metrics(row) for row in pair["contacts"]) + "</ul>" \
                if pair["contacts"] else '<p class="empty">未检测到接触；不生成代表点。</p>'
            cards.append(f'<details open><summary>{names}</summary>{_overlay(candidate, pair, layers, urls)}'
                         f'{contacts}<p>配对诊断：{_reasons(pair["qa_flags"])}</p></details>')
        body = "".join(cards) or "<p>当前没有可用图层配对。</p>"
        sections.append(f'<section><h2>{title}</h2><p>{_reasons(relation["reason_codes"])}</p>{body}</section>')
    return (PAGE_START + f'<img class="composite checker" src="{composite_url}" alt="PSD 合成图">'
            + "".join(sections) + "</body></html>")


PAGE_START = '''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>图层接触几何观察</title><style>
body{max-width:1100px;margin:24px auto;padding:0 20px;font:16px/1.6 system-ui,sans-serif;color:#203047;background:#f5f6f8}
h1{font-size:26px}h2{font-size:21px}.notice{padding:16px;background:#fff1ce;border-left:4px solid #a97600}
.checker{background-color:white;background-image:conic-gradient(#ddd 25%,transparent 0 50%,#ddd 0 75%,transparent 0);background-size:20px 20px}
.composite{display:block;width:100%;max-height:500px;object-fit:contain}svg{width:100%;max-height:620px;display:block;margin:12px auto}
section{margin:24px 0}details{background:white;padding:16px;margin:12px 0;border:1px solid #cad2df;border-radius:8px}
summary{font-weight:600;cursor:pointer;overflow-wrap:anywhere}p,li{overflow-wrap:anywhere}.empty{color:#855a00}
</style></head><body><h1>图层接触几何观察</h1>
<p class="notice">只读诊断。衣物原名配对并非身体语义认可；角色自身左右未知，不赋关节，不采用草稿。</p>
<p>各配对使用 PSD 画布坐标，原点在左上，Y 向下。青色与紫色框表示两个原图层边界；黄色框表示接触区域，红点仅为接触代表点。</p>'''
