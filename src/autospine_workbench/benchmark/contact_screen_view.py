"""Read-only diagnostic screen layered over the unchanged contact evidence page."""
from html import escape

from .contact_probe_view import RELATIONS, REASONS, render_contact_probe
from .contact_screen import validate_contact_screen

STATUS = {"rejected_deep_overlap": "深重叠排除", "review_required": "需复核",
          "local_contact_candidate": "局部接触候选"}
EXPLANATIONS = {
    **REASONS,
    "heuristic_clothing_proxy_not_anatomy": "衣物图层仅作几何代理，不能代表解剖结构",
    "relation_thresholds_uncalibrated": "该关系尚未校准阈值，保留人工复核",
    "gap_contact_requires_review": "存在间隙，需要复核接触是否成立",
    "clothing_overlap_too_deep": "衣物重叠范围过深，不适合作为局部关节接触",
    "clothing_overlap_ambiguous": "衣物重叠范围存在歧义，需检查图层结构",
    "local_geometry_only": "仅满足当前局部几何条件，尚未确认身体语义",
    "multiple_layer_pairs": "存在多个图层配对，需确认实际连接关系",
    "multiple_contact_regions": "存在多个接触区域，需确认连接位置",
}


def _reasons(codes):
    return "；".join(escape(EXPLANATIONS.get(code, "诊断项：" + str(code))) for code in codes) or "无额外诊断项"


def _summary(candidate, screen):
    layers = {row["layer_id"]: row for row in candidate["layers"]}
    summary = screen["summary"]
    counts = "；".join(f'{label} {summary[key]}' for key, label in STATUS.items())
    items = []
    for relation in screen["relations"]:
        pairs = []
        for pair in relation["pairs"]:
            names = " ↔ ".join(escape(layers[layer_id]["name"]) for layer_id in pair["layer_ids"])
            rows = []
            for contact in pair["contacts"]:
                ratio = contact["child_height_ratio"]
                ratio_text = "不适用" if ratio is None else f"{ratio:.4f}"
                rows.append(f'<li><strong>{STATUS[contact["geometry_status"]]}</strong> · '
                            f'<code>{escape(contact["contact_id"])}</code><br>'
                            f'接触框高度 / 子图层高度：{ratio_text}<br>'
                            f'{_reasons(contact["reason_codes"])}</li>')
            detail = "<ul>" + "".join(rows) + "</ul>" if rows else "<p>没有接触证据可筛选，不生成新位置。</p>"
            pairs.append(f'<details open><summary>{names}</summary><p>{_reasons(pair["reason_codes"])}</p>{detail}</details>')
        items.append(f'<section><h3>{RELATIONS[relation["relation"]]}</h3>'
                     f'<p>{_reasons(relation["reason_codes"])}</p>' + "".join(pairs) + "</section>")
    return ('<section id="contact-screen" aria-labelledby="contact-screen-title">'
            '<h2 id="contact-screen-title">接触筛选诊断</h2>'
            '<p class="notice">筛选阈值暂未校准。衣物代理的局部接触候选不代表批准；'
            '深重叠排除仅表示不适合作为局部关节接触假设，全部原始证据仍保留在下方。</p>'
            '<p>当前阈值仅用于髋部衣物配对；肩部与踝部不适用髋部阈值，统一进入复核。'
            '接触编号对应下方原始配对的接触证据，筛选不会移动代表点。</p>'
            f'<p>接触证据总数 {summary["total"]}；{counts}。</p>'
            + "".join(items) + '<hr></section>')


def render_contact_screen(candidate, probe, screen, composite, images):
    """Recompile the screen, then preserve every byte of the original evidence page."""
    screen = validate_contact_screen(candidate, probe, screen)
    page = render_contact_probe(candidate, probe, composite, images)
    prefix, marker, suffix = page.partition("</h1>")
    if not marker:
        raise ValueError("benchmark_contact_screen_view_heading_missing")
    return prefix + marker + _summary(candidate, screen) + suffix
