"""Paired repair diagnostic timelines, without recasting repaired rows as source."""
from html import escape
import json
from .ordinary_sleeve_repair import SCHEMA, PROFILE
from .ordinary_sleeve_review import STYLE, SCRIPT, REASONS


def render(document):
    if (document.get('schema') != SCHEMA or document.get('profile') != PROFILE
            or document.get('authority') != 'none' or document.get('production_authorized') is not False
            or document.get('global_replacement_authorized') is not False):
        raise ValueError('ordinary_sleeve_repair_review_source_invalid')
    cards, rows = [], []
    for record in document['records']:
        for key, title in [('before', '修正前'), ('selected_row', '当前候选选择')]:
            row = record[key]; index = len(rows)
            tracks = row.get('tracks') or []
            available = bool(tracks) and all(t.get('qa') and t.get('samples') for t in tracks)
            reasons = '；'.join(REASONS.get(c, c) for c in row['reason_codes'])
            status = '仍阻塞' if row['status'] == 'blocked' else '候选待复核'
            chosen = record['selected_trial'] or '保留原权重'
            name = escape(f"{record['layer_id']} / {record['component_id']} · {title}")
            cards.append(f'<section class="card" data-row="{index}"><h2>{name}</h2>'
                         f'<p class="state">{status}</p><p>{escape(reasons)}</p>'
                         f'<p>局部选择：{escape(chosen)}。选择不等于正式采用。</p>'
                         + ('<label>测试轨道 <select aria-label="测试轨道"></select></label>'
                            '<p class="qa" role="status"></p><svg role="img" aria-label="修正对比几何诊断"></svg>'
                            if available else '<p class="unavailable">无有效轨道；保留该区域的阻塞状态。</p>')
                         + '</section>')
            rows.append({k: row[k] for k in ('setup_vertices', 'triangles', 'tracks', 'setup_error') if k in row}
                        | {'available': available})
    payload = json.dumps(rows, ensure_ascii=False, allow_nan=False).replace('<', '\\u003c')
    title = escape(document['project_id'])
    provenance = ' · '.join(escape(f'{k}: {document[k]}') for k in
                            ('schema', 'profile', 'source_sha256', 'draft_sha256', 'skeleton_sha256', 'baseline_sha256'))
    # Reuse only the geometry player, never the uncorrected envelope contract.
    # Keep paired cards on the same track as well as the same timeline sample.
    synchronize = '''
document.querySelectorAll('.card select').forEach(select=>select.addEventListener('change',()=>{
  document.querySelectorAll('.card select').forEach(other=>{other.value=select.value;});draw();
}));
'''
    return (f'<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>{title} · 普通袖局部修正对比</title>'
            f'<meta name="viewport" content="width=device-width,initial-scale=1"><style>{STYLE}'
            'main{grid-template-columns:repeat(2,minmax(0,1fr))}.provenance{overflow-wrap:anywhere}'
            '@media(max-width:700px){main{grid-template-columns:1fr}}</style>'
            f'<header><h1>{title} · 普通袖局部修正候选</h1>'
            '<p>修正前与当前选择同步播放。四轨各 129 tick 检查，展示 33 个采样帧；失败和未支持区域继续保留。</p>'
            '<p>几何诊断未绘制纹理，尚未执行官方 Runtime 或透明接缝验证；不产生发布权或全局替换权。</p>'
            '<details><summary>修正来源</summary>'
            f'<p class="provenance">{provenance}</p></details>'
            '<div class="controls"><button id="play">播放</button><button id="setup">初始姿态</button>'
            '<label>时间轴 <input id="time" type="range" min="0" max="32" step="1" value="0"></label>'
            '<output id="clock"></output></div></header>'
            f'<main>{"".join(cards)}</main><script type="application/json" id="data">{payload}</script>'
            f'<script>{SCRIPT}{synchronize}</script></html>')
