"""Collect completed six-cell experiments without changing acceptance records."""
import argparse
from hashlib import sha256
from html import escape
import json
from pathlib import Path

CELLS=[('红美铃 squat','squat-temporal-correction-v1'),('Alice squat','squat-alice-temporal-v1'),
       ('辉夜 squat','squat-huiye-temporal-v1'),('红美铃 reach','reach-hongmeiling-temporal-v1'),
       ('Alice reach','reach-alice-temporal-v1'),('辉夜 reach','reach-huiye-temporal-v1')]


def run(root,output):
    records=[]
    for label,folder in CELLS:
        path=root/folder;raw=(path/'report.json').read_bytes();report=json.loads(raw)
        correction=json.loads((path/'correction.json').read_bytes())
        capture=json.loads((path/'runtime/report.json').read_bytes())
        geometry=json.loads((path/'deformation.json').read_bytes())
        if (report['runtime_status']!='passed' or not capture['passed']
                or capture['bundle_sha256']!=report['candidate_bundle_sha256']
                or len(capture['results'])!=report['sampled_frames']
                or geometry['skeleton_sha256']!=report['skeleton_sha256']):
            raise ValueError('temporal_pose_receipt_mismatch:'+folder)
        records.append(dict(label=label,folder=folder,report_sha256=sha256(raw).hexdigest(),
            candidate_bundle_sha256=report['candidate_bundle_sha256'],sampled_frames=report['sampled_frames'],
            runtime_status=report['runtime_status'],original_geometry_passed=report['geometry_passed'],
            inversion_samples=sum(r['inversion_samples'] for r in geometry['records']),
            proxy_failure_samples=len(correction['refinement'][-1]['check']['failures']),
            refinement_rounds=len(correction['refinement']),contact_status=report['contact_status'],depth_status=report['depth_status']))
    value=dict(profile='temporal-source-pose-six-cell-evidence-v1',authority='none',selected=False,
        records=records,total_runtime_frames=sum(r['sampled_frames'] for r in records),
        limitations=['sampled_not_continuous_time_proof','area_proxy_not_visual_acceptance',
                     'contact_depth_not_reintegrated','frame_counts_differ_from_previous_experiment'])
    with output.open('x',encoding='utf-8') as handle:json.dump(value,handle,ensure_ascii=False,indent=2)
    html='<meta charset="utf-8"><title>跨帧修正六组合</title><style>body{background:#15232e;color:white;font:18px sans-serif;margin:30px}a{color:#7ce4ef}td,th{padding:12px;border-bottom:1px solid #456}</style><h1>跨帧修正：六组合</h1><p>独立实验，未采用。接触与前后遮挡尚未重新接入；无翻转不代表动作视觉正确。</p><table><tr><th>角色/动作</th><th>采样帧</th><th>翻转累计次数</th><th>面积参考失败</th><th>原几何检查</th><th>官方捕获</th></tr>'
    for r in records:
        html+=f'<tr><td>{escape(r["label"])}</td><td>{r["sampled_frames"]}</td><td>{r["inversion_samples"]}</td><td>{r["proxy_failure_samples"]}</td><td>{"通过" if r["original_geometry_passed"] else "未通过"}</td><td><a href="{r["folder"]}/runtime/index.html">查看</a></td></tr>'
    (root/'temporal-review-v1.html').write_text(html+'</table>',encoding='utf-8')
    print(json.dumps(value,ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root',type=Path);parser.add_argument('output',type=Path)
    args=parser.parse_args();run(args.root,args.output)
