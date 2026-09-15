"""Explain current layer exceptions without granting new decisions."""
from html import escape

LABELS = {
    'binding_selection_required': '需要确认骨骼归属',
    'static_reference_not_bound': '仅保留静态参考，尚未绑定',
    'automatic_binding_evidence_stale': '自动绑定证据已过期，需重新检查',
    'automatic_binding_audit_needs_changes': '抽查发现问题，需修改绑定',
}


def render(row):
    details = {d['layer_id']: d for d in row.get('unresolved_layer_details', [])}
    items = []
    for key in row['unresolved_layers']:
        detail = details.get(key)
        if detail is None:
            items.append('<li>' + escape(key) + '</li>')
            continue
        title = escape(detail['name']) + ' · ' + escape(key)
        reasons = '<br>'.join(escape(LABELS.get(c, '待处理：' + c)) for c in detail['reason_codes'])
        regions = '、'.join(escape(r) for r in detail['region_ids'])
        items.append('<li><strong>' + title + '</strong><small>' + reasons +
                     ('<br>涉及区域：' + regions if regions else '') + '</small></li>')
    return ('<details><summary>待处理 ' + str(len(items)) + ' 层</summary><ul>' +
            ''.join(items) + '</ul></details>')
