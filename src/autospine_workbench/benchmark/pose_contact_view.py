"""Pose matching summary and the unchanged source contact evidence."""
from html import escape

from .contact_screen_view import render_contact_screen


def render_pose_contact_match(candidate, probe, screen, pose, doc, composite, images):
    from .pose_contact_match import validate_pose_contact_match

    validate_pose_contact_match(candidate, probe, screen, pose, doc)
    rows = []
    for row in doc['records']:
        status = '待复核候选' if row['status'] == 'candidate_requires_review' else '阻塞'
        position = '—' if row['position'] is None else ', '.join(f'{v:.2f}' for v in row['position'])
        reasons = '；'.join(escape(REASONS.get(reason, reason)) for reason in row['reason_codes'])
        rows.append(f'<tr><td>{escape(row["joint_id"])}</td><td>{status}</td><td>{position}</td><td>{reasons}</td></tr>')
    summary = doc['summary']
    content = ('<section id="pose-match"><h2>姿态与接触联合定位</h2>'
               '<p class="notice">只发布待复核候选。检测分数未经精度校准；衣物角色尚未确认，'
               '结果不写入人工草稿、骨架或生产决定。</p>'
               f'<p>待复核候选 {summary["candidate_requires_review"]}；阻塞 {summary["blocked"]} / 6。</p>'
               '<p>双侧必须使用不同接触区；近似同分、距离过远、低分或不可见姿态均不强行配对。</p>'
               '<table style="width:100%;text-align:left;border-spacing:12px"><thead><tr>'
               '<th>关节</th><th>状态</th><th>候选坐标</th><th>原因</th></tr></thead><tbody>'
               + ''.join(rows) + '</tbody></table></section>')
    page = render_contact_screen(candidate, probe, screen, composite, images)
    prefix, marker, suffix = page.partition('</h1>')
    if not marker:
        raise ValueError('benchmark_pose_match_view_invalid')
    return prefix + marker + content + suffix


REASONS = {
    'pose_observations_required': '缺少绑定当前合成图的真实姿态观测',
    'semantic_roles_unreviewed': '身体与衣物角色尚未复核',
    'heuristic_only': '仅启发式候选，不是校准概率',
}
