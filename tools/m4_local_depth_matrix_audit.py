"""Audit matrix coverage separately from candidate quality and reused Runtime evidence."""
import argparse
from collections import Counter
from hashlib import sha256
from html import escape
import json
from pathlib import Path
from autospine_workbench.targets.character43.local_depth_summary import summarize
from m4_motion_cohort import digest


def audit(plan,cohort,state,folder):
    if state['identity']['plan_sha256']!=digest(plan) or cohort['plan_sha256']!=digest(plan):
        raise ValueError('matrix_audit_plan_identity')
    expected={m['id']+'/'+c['id'] for m in plan['motions'] for c in plan['characters']}
    if set(state['cells'])-expected:raise ValueError('matrix_audit_unplanned_cells')
    rows=[];totals=Counter()
    for key in sorted(expected):
        saved=state['cells'].get(key)
        if saved is None:rows.append(dict(cell=key,status='pending'));continue
        raw=(folder/saved['file']).read_bytes()
        if sha256(raw).hexdigest()!=saved['report_sha256']:raise ValueError('matrix_audit_report_changed')
        report=json.loads(raw);baseline=cohort['cells'][key]
        if (report['job_id']!=baseline['job_id'] or saved['job_id']!=report['job_id'] or report['artifact_sha256']!=baseline['result']['artifact_sha256']
                or saved['artifact_sha256']!=report['artifact_sha256']):
            raise ValueError('matrix_audit_candidate_identity')
        causes=summarize(report['records'])
        if causes!=saved['causes']:raise ValueError('matrix_audit_causes_changed')
        counts=Counter(r['check']['status'] for r in report['records'])
        if dict(counts)!=report['counts'] or dict(counts)!=saved['counts']:raise ValueError('matrix_audit_counts_changed')
        reasons=Counter()
        for pair in causes['pairs']:reasons.update(pair['reasons'])
        totals.update(counts)
        incomplete=bool(counts['unmeasured'] or report.get('failure') or not report['records'])
        rows.append(dict(cell=key,status='incomplete' if incomplete else 'measured',
            job_id=report['job_id'],artifact_sha256=report['artifact_sha256'],report_sha256=saved['report_sha256'],
            counts=dict(counts),reasons=dict(reasons),
            prior_geometry_passed=baseline['result']['geometry_passed'],
            prior_runtime_frames=baseline['result']['runtime']['frames'],
            prior_contact_status=baseline['result']['contact_status']))
    measured=[r for r in rows if r['status']!='pending']
    return dict(profile='frozen-matrix-local-depth-audit-v1',plan_sha256=digest(plan),
        planned=len(expected),processed=len(measured),pending=len(expected)-len(measured),
        fully_measured=sum(r['status']=='measured' for r in rows),
        incomplete=sum(r['status']=='incomplete' for r in rows),counts=dict(totals),rows=rows,
        authority='none',selected=False,
        scope='diagnostic_coverage_and_prior_candidate_evidence_not_new_runtime_or_visual_acceptance')


def render(result):
    rows=[]
    for row in result['rows']:
        if row['status']=='pending':
            rows.append(f'<tr><td>{escape(row["cell"])}</td><td>待处理</td><td colspan="3">—</td></tr>');continue
        labels='；'.join(f'{k}: {v}' for k,v in row['counts'].items())
        geometry='通过' if row['prior_geometry_passed'] else '未通过'
        rows.append(f'<tr><td>{escape(row["cell"])}</td><td>{escape(labels)}</td>'
                    f'<td>{geometry}</td><td>{escape(row["prior_contact_status"])}</td><td>{row["prior_runtime_frames"]}</td></tr>')
    return ('<!doctype html><meta charset="utf-8"><title>M4 覆盖与质量审计</title>'
        '<style>body{font:16px sans-serif;background:#182531;color:#eee;margin:24px}td,th{padding:12px;border-bottom:1px solid #54616d;text-align:left}</style>'
        f'<h1>覆盖与质量分开核对</h1><p>已处理 {result["processed"]}/{result["planned"]}；'
        f'全部样本测得 {result["fully_measured"]}；含缺失 {result["incomplete"]}；待处理 {result["pending"]}。</p>'
        '<p>全部样本测得不代表遮挡、几何或视觉通过。几何、接触与 Runtime 帧数来自冻结候选的已有证据，本次未重新捕获；未自动验收。</p>'
        '<p>uniform_* 是深度代理的单一方向，requires_partition_or_more_depth 是局部歧义，unmeasured 是未测。均不是正确率。</p>'
        '<table><tr><th>动作 / 角色</th><th>局部深度样本</th><th>已有几何检查</th><th>已有接触状态</th><th>已有 Runtime 帧数</th></tr>'+''.join(rows)+'</table>')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('plan','cohort','folder','output'):parser.add_argument(name,type=Path)
    args=parser.parse_args();state=json.loads((args.folder/'state.json').read_bytes())
    if state['identity']['cohort_sha256']!=sha256(args.cohort.read_bytes()).hexdigest():raise ValueError('matrix_audit_cohort_changed')
    result=audit(json.loads(args.plan.read_bytes()),json.loads(args.cohort.read_bytes()),state,args.folder)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    args.output.with_suffix('.html').write_text(render(result),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='rows'}))
