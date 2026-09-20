"""Human-readable fixed-cohort matrix without changing acceptance evidence."""
from html import escape


def render(report):
    labels={'passed':'Runtime 已验证','failed':'Runtime 失败','missing':'动作缺失','unmeasured':'缺少完整采样'}
    rows=[]
    for character in report['characters']:
        motions=''.join(f'<td>{escape(labels[m["status"]])}<br>{m["sampled_frames"]} 帧</td>' for m in character['motions'])
        pending='、'.join(character['unresolved_layers']) or '无'
        rows.append(f'<tr><th>{escape(character["name"])}</th>{motions}'
            f'<td>{escape(pending)}</td><td>{"通过" if character["visual_accepted"] else "待复核"}</td>'
            f'<td>{"完成" if character["completed"] else "未完成"}</td></tr>')
    metrics=report['metrics']
    measured_html = ''
    audit = metrics.get('auto_binding_audit')
    if audit:
        rate = '未测量' if audit['sampled_error_rate'] is None else f'{audit["sampled_error_rate"]*100:.1f}%'
        measured_html += (f'<p>自动绑定抽查：明确判断 {audit["assessed_bindings"]}/{audit["eligible_bindings"]} 项；'
                          f'需修改 {audit["incorrect"]} 项；样本错误率 {rate}。人工所选样本不代表全部输入精度。</p>')
    for label, timing, count, total in [
        ('视觉复核', metrics.get('visual_review_timing'), 'measured_characters', 'total_characters'),
        ('自动绑定抽查', (audit or {}).get('audit_timing'), 'measured_projects', 'total_projects')]:
        if timing:
            duration = '未测量' if timing['measured_minutes'] is None else f'{timing["measured_minutes"]:g} 分钟'
            measured_html += f'<p>{label}会话计时：{timing[count]}/{timing[total]} 个角色；已测部分 {duration}。缺失时间不按零计算。</p>'
    return ('<!doctype html><meta charset="utf-8"><title>三角色多动作验收</title>'
        '<style>body{font:16px system-ui;background:#15212c;color:#eee;margin:32px}'
        'table{border-collapse:collapse;width:100%}td,th{padding:16px;border:1px solid #536675;text-align:left}'
        'th{background:#203544}p{line-height:1.7}</style><h1>固定三角色 · 多动作验收</h1>'
        f'<p>整角色完成 {metrics["completed_characters"]}/{metrics["total_characters"]}；'
        f'目标动作 Runtime 通过 {metrics["runtime_passed_motion_cases"]}/{metrics["required_motion_cases"]}。</p>'
        '<p>动作检查通过不代表整角色完成。绑定待办和人工视觉复核分别保留。</p>'
        '<table><tr><th>角色</th><th>待机</th><th>左手挥动</th><th>行走</th><th>待处理图层</th><th>视觉复核</th><th>整体</th></tr>'
        +''.join(rows)+'</table>'+measured_html+'<p>人工总耗时：未测量。错误自动采用率：未测量，缺少独立标注。'
        '该角色集用于开发集成验证，不作为独立保留集精度证明。</p>').encode('utf-8')
