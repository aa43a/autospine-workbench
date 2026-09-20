"""Readable matrix from exact frozen cohort jobs; unknown gates stay unknown."""
from html import escape
import json
from pathlib import Path
import sys
from m4_motion_cohort import digest
from m4_motion_cohort_reviews import decision

LABELS = {'succeeded': '捕获完成', 'running': '运行中', 'pending': '排队中', 'failed': '任务失败',
    'not_started': '尚未开始', 'needs_review': '待阶段验收', 'needs_changes': '存在异常',
    'not_evaluated': '未检查', 'unavailable_no_labels': '无源接触标签',
    'ankle_proxy_corrected': '已修正踝部滑移', 'ankle_proxy_passed': '踝部支点通过',
    'inferred_partial_corrected': '部分源区间已修正，其余未验证',
    'inferred_proxy_corrected': '推断支撑已修正', 'inferred_proxy_passed': '推断支撑通过',
    'inferred_proxy_drift': '推断支撑仍有滑移',
    'depth_candidates_need_review': '遮挡需处理', 'depth_overlap_no_change': '采样遮挡无需改序',
    'evidence_incomplete': '证据不完整', 'stage_review': '可阶段复核',
    'accepted': '阶段接受', 'accepted_with_exceptions': '阶段接受，保留异常',
    'rejected': '需要调整', 'revoked': '已撤销', 'evidence_changed': '证据已变化，需复核',
    'True': '通过', 'False': '失败', 'None': '无证据'}


def label(value):
    return LABELS.get(str(value), str(value))


def rows(plan, state, reviews=None):
    if state.get('plan_sha256') is not None and state['plan_sha256'] != digest(plan):
        raise ValueError('cohort_plan_identity_mismatch')
    if reviews is not None and reviews.get('plan_sha256') != digest(plan):
        raise ValueError('cohort_review_plan_mismatch')
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
            readiness = diagnostic.get('readiness', {})
            if readiness and readiness.get('artifact_sha256') != result.get('artifact_sha256'):
                raise ValueError('cohort_readiness_artifact_mismatch')
            if diagnostic.get('profiles') and any(diagnostic['profiles'].get(k) != v
                    for k, v in plan.get('expected_profiles', {}).items()):
                raise ValueError('cohort_report_execution_profile_mismatch')
            visual, visual_record = decision(reviews, key, job, readiness)
            status = job.get('status', 'not_started')
            if source_job.get('status') in ('failed', 'cancelled', 'interrupted') and not job:
                status = 'source_' + source_job['status']
            output.append(dict(cell=key, status=status, job_id=job.get('job_id'),
                geometry=result.get('geometry_passed'),
                candidate=result.get('character_animation_status', 'not_evaluated'),
                contact=result.get('contact_status', 'not_evaluated'),
                depth=result.get('depth_order_status', 'not_evaluated'),
                readiness=readiness.get('status', 'not_evaluated'),
                stages=readiness.get('stages', []),
                profiles=diagnostic.get('profiles', {}),
                visual=visual, visual_record=visual_record, issues=issues,
                geometry_failures=[r for r in diagnostic.get('geometry', {}).get('records', []) if not r['passed']],
                runtime_frames=result.get('runtime', {}).get('frames'),
                runtime_geometry=result.get('runtime', {}).get('geometry_status', 'not_evaluated'),
                failure=job.get('reason_code') or source_job.get('reason_code'),
                artifact_sha256=result.get('artifact_sha256')))
    return output


def render(plan, state, reviews=None):
    records = rows(plan, state, reviews)
    lines = []
    for row in records:
        job = row['job_id']
        url = '/api/motions/' + job + '/view/' if job else ''
        links = (f'<a href="http://127.0.0.1:8918{escape(url)}player.html">播放/时间轴</a> · '
                 f'<a href="http://127.0.0.1:8918{escape(url)}contact.html">接触定位</a> · '
                 f'<a href="http://127.0.0.1:8918{escape(url)}depth.html">遮挡定位</a>') if row['status'] == 'succeeded' else ''
        for failure in row['geometry_failures']:
            first = failure.get('first_failure')
            if first:
                caption = escape(failure['slot']) + ' @ ' + str(round(first['time'], 3)) + 's'
                links += f'<br><a href="http://127.0.0.1:8918{escape(url)}player.html?time={first["time"]}">{caption}</a>'
        gate_notes = [s['stage'] + ': ' + s['explanation'] for s in row['stages']
                      if s['status'] != 'sampled_pass']
        values = [row['cell'], row['status'], row['candidate'], row['readiness'], str(row['geometry']), row['runtime_frames'],
                  row['contact'], row['depth'], label(row['visual']) +
                  ((' · ' + row['visual_record']['notes']) if row['visual_record'] else ''),
                  '\n'.join(gate_notes) or (json.dumps(row['issues'], ensure_ascii=False)
                    if row['issues'] else row['failure'] or '—')]
        lines.append('<tr>' + ''.join('<td>'+escape(label(v))+'</td>' for v in values) + '<td>'+links+'</td></tr>')
    counts = summary(records)
    heading = (f'<p>固定组合 {counts["required"]} · 已结束 {counts["terminal"]} · '
        f'完成 Runtime 捕获 {counts["captured"]} · 几何通过 {counts["geometry_passed"]} · '
        f'存在候选异常 {counts["candidate_exceptions"]} · 任务失败 {counts["failed"]}</p>')
    heading += (f'<p>人工阶段接受 {counts["visual_accepted"]} · 保留异常接受 '
                f'{counts["visual_accepted_with_exceptions"]} · 验收证据已变化 {counts["visual_evidence_changed"]}。'
                + ('验收快照：' + escape(reviews['captured_at']) if reviews else '未读取人工验收记录。') + '</p>')
    return '''<!doctype html><meta charset="utf-8"><title>M4 固定动作验收矩阵</title>
<style>body{background:#101923;color:#e3edf6;font:15px system-ui;padding:24px}table{border-collapse:collapse;width:100%}td,th{border:1px solid #425466;padding:10px;text-align:left}a{color:#69d4fa}td{max-width:300px;overflow-wrap:anywhere}</style>
<h1>M4 三结构角色 × 八类动作</h1><p>固定完整源动作、正面投影；失败保留，不替换为更容易通过的样本。类别仍需核对实际动作。</p>
<p>任务完成不等于动作通过。接触、遮挡、视觉验收分别列出，未检查不计通过。此页为生成时快照。</p>
''' + heading + '<table><thead><tr>' + ''.join('<th>'+v+'</th>' for v in ['动作/角色','任务','候选','综合检查','几何','Runtime 帧','接触','遮挡','人工视觉','异常','定位']) + '</tr></thead><tbody>' + ''.join(lines) + '</tbody></table>'


def summary(records):
    return dict(required=len(records),
        terminal=sum(r['status'] in ('succeeded', 'failed', 'cancelled', 'canceled', 'interrupted') or r['status'].startswith('source_') for r in records),
        captured=sum(r['status']=='succeeded' and bool(r['runtime_frames']) for r in records),
        geometry_passed=sum(r['geometry'] is True for r in records),
        candidate_exceptions=sum(r['candidate']=='needs_changes' or r['readiness']=='needs_changes' for r in records),
        failed=sum(r['status']=='failed' or r['status'].startswith('source_') for r in records),
        runtime_frames=sum(r['runtime_frames'] or 0 for r in records),
        visual_accepted=sum(r['visual']=='accepted' for r in records),
        visual_accepted_with_exceptions=sum(r['visual']=='accepted_with_exceptions' for r in records),
        visual_evidence_changed=sum(r['visual']=='evidence_changed' for r in records),
        stage_review_ready=sum(r['readiness']=='stage_review' for r in records),
        contact_partial=sum(r['contact']=='inferred_partial_corrected' for r in records),
        contact_unmeasured=sum(r['contact'] in ('not_evaluated', 'unavailable_no_labels') for r in records),
        depth_unmeasured=sum(r['depth']=='not_evaluated' for r in records))


if __name__ == '__main__':
    plan, state = [json.loads(Path(p).read_text(encoding='utf-8')) for p in sys.argv[1:3]]
    reviews = json.loads(Path(sys.argv[4]).read_text(encoding='utf-8')) if len(sys.argv) > 4 else None
    Path(sys.argv[3]).write_text(render(plan, state, reviews), encoding='utf-8')
    Path(sys.argv[3]).with_suffix('.json').write_text(json.dumps({
        'schema': 'autospine.motion-cohort-report/v1', 'plan_sha256': digest(plan),
        'rows': rows(plan, state, reviews), 'summary': summary(rows(plan, state, reviews)),
        'visual_snapshot_at': reviews.get('captured_at') if reviews else None,
        'authority': 'none', 'production_authorized': False},
        ensure_ascii=False, indent=2), encoding='utf-8')
