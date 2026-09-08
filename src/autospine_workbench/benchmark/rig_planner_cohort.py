"""Compare full-source strategy distributions without claiming accuracy."""
from collections import Counter
from html import escape
from urllib.parse import quote
from ..asset.planning.rig_planner import PROFILE
from ..resolved_project import canonical_sha256
from .rig_planner_view import LABELS


def summarize(entries):
    if not entries:
        raise ValueError('planner_cohort_empty')
    rows = []; seen = set()
    for label, plan, inventory in entries:
        if (plan['profile'] != PROFILE or plan['authority'] != 'none'
                or plan['production_authorized'] is not False or plan['scope'] != inventory
                or [r['layer_id'] for r in plan['layers']] != inventory
                or len(set(inventory)) != len(inventory)):
            raise ValueError('planner_cohort_incomparable')
        if plan['character_id'] in seen:
            raise ValueError('planner_cohort_duplicate_character')
        seen.add(plan['character_id'])
        layers = plan['layers']
        rows.append({'label': label, 'character_id': plan['character_id'],
            'plan_sha256': canonical_sha256(plan), 'source_draft_sha256': plan['source_draft_sha256'],
            'total_layers': len(layers),
            'strategies': dict(sorted(Counter(r['strategy'] for r in layers).items())),
            'pending_strategies': dict(sorted(Counter(r['strategy'] for r in layers
                                                     if r['existing_action'] == 'pending').items())),
            'existing_actions': dict(sorted(Counter(r['existing_action'] for r in layers).items())),
            'reason_counts': dict(sorted(Counter(c for r in layers for c in r['reason_codes']).items())),
            'review_items': [{'layer_id': r['layer_id'], 'name': r['name'],
                              'reason_codes': r['reason_codes']} for r in layers if r['strategy']=='semantic_review']})
    return {'schema': 'autospine.rig-plan-cohort/v1', 'profile': PROFILE,
        'scope_policy': 'all_source_layers', 'characters': rows,
        'total_layers': sum(r['total_layers'] for r in rows), 'accuracy': None,
        'authority': 'none', 'production_authorized': False, 'status': 'needs_review'}


def render(report):
    headers = ''.join('<th>'+escape(label)+'</th>' for label in LABELS.values())
    rows = []
    for row in report['characters']:
        cells = ''.join(f"<td>{row['strategies'].get(k,0)} / {row['pending_strategies'].get(k,0)}</td>" for k in LABELS)
        rows.append(f"<tr><th><a href='{quote(row['label'], safe='')}/review.html'>{escape(row['label'])}</a></th><td>{row['total_layers']}</td>{cells}</tr>")
    reviews = ''.join('<li>'+escape(row['label'])+'：'+escape('、'.join(
        r['name']+' ('+r['layer_id']+')' for r in row['review_items']) or '无')+'</li>' for row in report['characters'])
    return f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Rig Planner 跨角色比较</title><style>body{{font:16px/1.6 system-ui;margin:30px;color:#233548;background:#f5f7fa}}
table{{border-collapse:collapse;background:white}}td,th{{padding:12px;border:1px solid #ccd}}.scroll{{overflow:auto}}</style>
<h1>Rig Planner 跨角色比较</h1><p>同一版规则、全部源图层，共 {report['total_layers']} 层。
每格为「全部层数 / 其中整层 pending 数」。已有选择保持原状；新策略不会覆盖它们。</p>
<div class="scroll"><table><tr><th>角色</th><th>总层数</th>{headers}</tr>{''.join(rows)}</table></div>
<h2>需语义或几何复核的层</h2><ul>{reviews}</ul>
<p>这些是开发样本的策略分布，不是准确率，也不是自动采用率。尚无独立策略标注；没有改变动画或授予生产权。</p></html>'''
