"""Readable matrix from exact frozen cohort jobs; unknown gates stay unknown."""
from html import escape
import json
from pathlib import Path
import sys
from m4_motion_cohort import digest

LABELS = {'succeeded': '捕获完成', 'running': '运行中', 'pending': '排队中', 'failed': '任务失败',
    'not_started': '尚未开始', 'needs_review': '待阶段验收', 'needs_changes': '存在异常',
    'not_evaluated': '未检查', 'unavailable_no_labels': '无源接触标签',
    'ankle_proxy_corrected': '已修正踝部滑移', 'ankle_proxy_passed': '踝部支点通过',
    'True': '通过', 'False': '失败', 'None': '无证据'}


def label(value):
    return LABELS.get(str(value), str(value))


def rows(plan, state):
    if state.get('plan_sha256') is not None and state['plan_sha256'] != digest(plan):
        raise ValueError('cohort_plan_identity_mismatch')
    output = []
    for source in plan['motions']:
        for character in plan['characters']:
            key = source['id'] + '/' + character['id']
            source_job = state['sources'].get(source['id'], {})
            job = state['cells'].get(key, {})
            result = job.get('result', {})
            issues = result.get('issues', [])
            diagnostic = state.get('diagnostics', {}).get(key, {})
            if diagnostic and diagnostic['job_id'] != job.get('job_id'):
                raise ValueError('cohort_diagnostic_job_mismatch')
            status = job.get('status', 'not_started')
            if source_job.get('status') in ('failed', 'cancelled', 'interrupted') and not job:
                status = 'source_' + source_job['status']
            output.append(dict(cell=key, status=status, job_id=job.get('job_id'),
                geometry=result.get('geometry_passed'),
                candidate=result.get('character_animation_status', 'not_evaluated'),
                contact=result.get('contact_status', 'not_evaluated'),
                depth=result.get('depth_order_status', 'not_evaluated'),
                visual='not_evaluated', issues=issues,
                geometry_failures=[r for r in diagnostic.get('geometry', {}).get('records', []) if not r['passed']],
                runtime_frames=result.get('runtime', {}).get('frames'),
                runtime_geometry=result.get('runtime', {}).get('geometry_status', 'not_evaluated'),
                failure=job.get('reason_code') or source_job.get('reason_code'),
                artifact_sha256=result.get('artifact_sha256')))
    return output


def render(plan, state):
    records = rows(plan, state)
    lines = []
    for row in records:
        job = row['job_id']
        url = '/api/motions/' + job + '/view/' if job else ''
        links = (f'<a href="http://127.0.0.1:8918{escape(url)}player.html">播放/时间轴</a> · '
                 f'<a href="http://127.0.0.1:8918{escape(url)}contact.html">接触定位</a>') if row['status'] == 'succeeded' else ''
        for failure in row['geometry_failures']:
            first = failure.get('first_failure')
            if first:
                caption = escape(failure['slot']) + ' @ ' + str(round(first['time'], 3)) + 's'
                links += f'<br><a href="http://127.0.0.1:8918{escape(url)}player.html?time={first["time"]}">{caption}</a>'
        values = [row['cell'], row['status'], row['candidate'], str(row['geometry']), row['runtime_frames'],
                  row['contact'], row['depth'], row['visual'],
                  json.dumps(row['issues'], ensure_ascii=False) if row['issues'] else row['failure'] or '—']
        lines.append('<tr>' + ''.join('<td>'+escape(label(v))+'</td>' for v in values) + '<td>'+links+'</td></tr>')
    return '''<!doctype html><meta charset="utf-8"><title>M4 固定动作验收矩阵</title>
<style>body{background:#101923;color:#e3edf6;font:15px system-ui;padding:24px}table{border-collapse:collapse;width:100%}td,th{border:1px solid #425466;padding:10px;text-align:left}a{color:#69d4fa}td{max-width:300px;overflow-wrap:anywhere}</style>
<h1>M4 三结构角色 × 八类动作</h1><p>固定完整源动作、正面投影；失败保留，不替换为更容易通过的样本。类别仍需核对实际动作。</p>
<p>任务完成不等于动作通过。接触、遮挡、视觉验收分别列出，未检查不计通过。此页为生成时快照。</p>
<table><thead><tr>''' + ''.join('<th>'+v+'</th>' for v in ['动作/角色','任务','候选','几何','Runtime 帧','接触','遮挡','人工视觉','异常','定位']) + '</tr></thead><tbody>' + ''.join(lines) + '</tbody></table>'


if __name__ == '__main__':
    plan, state = [json.loads(Path(p).read_text(encoding='utf-8')) for p in sys.argv[1:3]]
    Path(sys.argv[3]).write_text(render(plan, state), encoding='utf-8')
    Path(sys.argv[3]).with_suffix('.json').write_text(json.dumps({
        'schema': 'autospine.motion-cohort-report/v1', 'plan_sha256': digest(plan),
        'rows': rows(plan, state), 'authority': 'none', 'production_authorized': False},
        ensure_ascii=False, indent=2), encoding='utf-8')
