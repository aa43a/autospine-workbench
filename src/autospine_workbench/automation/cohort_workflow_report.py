"""Read-only first-ten acceptance matrix; never creates or upgrades evidence."""
from html import escape
from urllib.parse import quote, urlsplit


LABELS = dict(character_candidate_missing='尚未构建整角色候选',
    automatic_binding_audit_needs_changes='自动绑定抽查发现需修改项',
    required_animations_missing='缺少必需动作', required_motion_runtime_incomplete='动作 Runtime 验证不完整',
    runtime_unmeasured='Runtime 尚未测量', runtime_failed='Runtime 检查失败',
    geometry_not_passed='几何检查尚未通过', layer_inventory_missing='尚无整角色图层库存',
    layer_binding_incomplete='还有图层绑定待处理', automatic_binding_evidence_stale='自动绑定证据已过期',
    whole_character_visual_review_required='等待整角色视觉复核',
    psd_variant_review_required='需要选择 PSD 版本', character_route_confirmation_required='需要确认普通肢体或袖装路线',
    character_source_unavailable='需要准备或复核动画来源', animated_source_missing='尚未准备动画来源',
    character_sleeve_unavailable='袖装候选尚不可用')


def render(report, base_url):
    origin = urlsplit(base_url)
    if (origin.scheme != 'http' or origin.hostname not in ('localhost', '127.0.0.1')
            or origin.path or origin.query or origin.fragment or origin.username or origin.password):
        raise ValueError('cohort_report_local_origin_required')
    base_url = 'http://' + origin.hostname + (':' + str(origin.port) if origin.port is not None else '')
    if report.get('schema') != 'autospine.cohort-workflow/v1':
        raise ValueError('cohort_report_schema_required')
    rows = []
    statuses = dict(passed='已验证', failed='失败', missing='缺失', unmeasured='未测量')
    for row in report['characters']:
        project = row['project_id']
        title = escape(row['name'])
        if project:
            title = f'<a href="{base_url}/?project={quote(project, safe="")}">{title}</a>'
        candidate = '尚无候选'
        if project and row['job_id'] and row['artifact_sha256']:
            url = (base_url + '/api/projects/' + quote(project, safe='') +
                   '/automation/character/jobs/' + quote(row['job_id'], safe='') + '/view/index.html')
            candidate = f'<a href="{url}">查看本次候选</a>'
        pending = row['unresolved_layers']
        if 'layer_inventory_missing' in row['reason_codes']:
            binding = '尚无图层库存'
        elif pending:
            from .cohort_layer_details import render as render_layers
            binding = render_layers(row)
        else:
            binding = '绑定完整'
        motions = {m['animation']: m for m in row['motions']}
        cells = []
        for animation in report['required_animations']:
            m = motions.get(animation)
            status = m['status'] if m else 'missing'
            frames = m['sampled_frames'] if m else 0
            cells.append(f'<td class="{status if status in statuses else "unmeasured"}">'
                         f'{statuses.get(status, "未测量")}<small>{frames} 帧</small></td>')
        geometry = '待通过' if 'geometry_not_passed' in row['reason_codes'] else '已通过'
        visual = '已接受' if row['visual_accepted'] else '待复核'
        reasons = [LABELS.get(code, '待处理：' + code) for code in row['reason_codes']]
        reason_html = '<br>'.join(escape(text) for text in reasons) or '当前候选验收完成'
        timing = row.get('visual_review_session_minutes')
        timing_html = '未计时' if timing is None else f'{timing:g} 分钟（视觉会话）'
        rows.append('<tr><th>' + title + '<small>' + candidate + '</small></th><td>' + binding +
                    '</td><td>' + geometry + '</td>' + ''.join(cells) + '<td>' + visual +
                    '<small>' + timing_html + '</small></td><td>' +
                    ('完成' if row['completed'] else '未完成') + '<details><summary>全部原因</summary>' +
                    reason_html + '</details></td></tr>')
    metrics = report['metrics']
    timing = metrics.get('visual_review_timing'); timing_summary = ''
    if timing:
        duration = '未测量' if timing['measured_minutes'] is None else f'{timing["measured_minutes"]:g} 分钟'
        timing_summary = (f'<p>当前候选视觉复核计时：{timing["measured_characters"]}/{timing["total_characters"]} 名角色；'
                          f'已测部分合计 {duration}。未计时部分不按零计算，不包含标注、修正或历史返工耗时。</p>')
    audit = metrics.get('auto_binding_audit'); audit_html = ''
    if audit:
        rate = '未测量' if audit['sampled_error_rate'] is None else f'{audit["sampled_error_rate"]*100:.1f}%'
        audit_html = (f'<p>自动绑定抽查：明确判断 {audit["assessed_bindings"]}/{audit["eligible_bindings"]} 项，'
                      f'需修改 {audit["incorrect"]} 项，无法判断 {audit["unobservable"]} 项；抽查错误率 {rate}。'
                      '这是人工所选样本，不是全部输入的准确率。</p>')
    labels = {'idle': '待机', 'wave-left': '左手挥动', 'walk': '行走'}
    headers = ''.join('<th>' + escape(labels.get(a, a)) + '</th>' for a in report['required_animations'])
    return ('<!doctype html><html lang="zh-CN"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1"><title>首批十角色验收进度</title>'
        '<style>body{background:#172330;color:#eee;font:16px system-ui;margin:24px;line-height:1.6}'
        'td,th{padding:12px;border:1px solid #567;vertical-align:top;text-align:left}'
        'a{color:#7de0ff}table{border-collapse:collapse;min-width:1000px;width:100%}'
        '.matrix{overflow:auto}small{display:block;font-size:13px;color:#c0cddd}'
        '.passed{color:#8ce6b1}.failed{color:#ffaaa9}summary{cursor:pointer}ul{padding-left:20px}</style>'
        '<h1>首批十角色 · 验收矩阵</h1><p>整角色完成 '
        f'{metrics["completed_characters"]}/{metrics["total_characters"]}；必需动作验证 '
        f'{metrics["runtime_passed_motion_cases"]}/{metrics["required_motion_cases"]}；已测角色 '
        f'{metrics["runtime_measured_characters"]}/{metrics["total_characters"]}。</p>'
        '<p>这是读取时的快照，不会自动刷新。项目有新修改时，请重新生成；候选入口指向本次读取的版本。</p>'
        '<p>先处理绑定和几何问题，再完成动作及整角色视觉验收。动作已验证不代表绑定或视觉已接受。</p>'
        '<div class="matrix"><table><thead><tr><th>角色 / 候选</th><th>图层绑定</th><th>几何</th>' +
        headers + '<th>人工视觉</th><th>整角色</th></tr></thead><tbody>' + ''.join(rows) +
        '</tbody></table></div>' + timing_summary + audit_html + '<p>人工总耗时：未测量。错误自动采用率：未测量。'
        '单次视觉计时不代表全部人工耗时；这些角色不作为独立 holdout 精度证明。</p></html>')
