"""Compact, non-authoritative support view over identity-checked cohort rows."""
from html import escape

STAGES = ('投影', '几何', '接触', '遮挡', 'Runtime')
LABELS = {'sampled_pass': '采样通过', 'needs_changes': '需处理', 'unmeasured': '未知'}


def gates(row):
    stages = row.get('stages', [])
    result = {}
    for name in STAGES:
        matches = [s for s in stages if s.get('stage') == name]
        if len(matches) > 1:
            raise ValueError('cohort_duplicate_readiness_stage')
        status = matches[0].get('status') if matches else None
        result[name] = status if status in LABELS else 'unmeasured'
    return result


def coverage(records):
    return {name: {state: sum(gates(row)[name] == state for row in records)
                   for state in LABELS} for name in STAGES}


def render(plan, records):
    indexed = {r['cell']: r for r in records}
    if len(indexed) != len(records):
        raise ValueError('cohort_duplicate_cell')
    parts = ['<h2>动作范围总览</h2><p>仅针对本批固定来源和视角；采样通过不代表任意动作受支持。'
             '点击组合查看异常与播放入口。缺失证据不计通过。</p><table><thead><tr><th>动作</th>']
    parts.extend('<th>' + escape(c['id']) + '</th>' for c in plan['characters'])
    parts.append('</tr></thead><tbody>')
    for motion in plan['motions']:
        parts.append('<tr><th>' + escape(motion['id']) + '</th>')
        for character in plan['characters']:
            key = motion['id'] + '/' + character['id']
            row = indexed[key]
            states = gates(row)
            notes = ' · '.join(name + '：' + LABELS[state] for name, state in states.items())
            # Keep extra correction gates and incomplete readiness visible too.
            ready = row.get('readiness') == 'stage_review' and all(
                state == 'sampled_pass' for state in states.values())
            title = '可阶段复核' if ready else '存在异常或待验证'
            parts.append('<td><a href="#cell-' + escape(key, quote=True) + '">' + title
                         + '</a><br>' + escape(notes) + '</td>')
        parts.append('</tr>')
    parts.append('</tbody></table><h3>检查覆盖</h3><ul>')
    for name, counts in coverage(records).items():
        parts.append('<li>' + name + '：' + ' · '.join(
            LABELS[state] + ' ' + str(count) for state, count in counts.items()) + '</li>')
    parts.append('</ul>')
    return ''.join(parts)
