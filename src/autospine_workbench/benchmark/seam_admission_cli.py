"""Hash-bound review-only relation gates from official Runtime observations."""
import argparse
import hashlib
import html
import json
from pathlib import Path
from ..resolved_project import canonical_sha256
from ..targets.spine43.seam_admission import evaluate


def compile_report(direct_path,runtime_path,candidate_path,manifest_path):
    raw=[p.read_bytes() for p in (direct_path,runtime_path,candidate_path,manifest_path)]
    direct,runtime,candidate,manifest=[json.loads(r) for r in raw]
    sha=lambda r:hashlib.sha256(r).hexdigest()
    if sha(raw[0])!=runtime['direct_report_sha256'] or sha(raw[3])!=runtime['bundle_manifest_sha256']['after']:raise ValueError('admission_source_identity')
    if 'preview-manifest.json' in candidate['files']:
        if candidate['files']['preview-manifest.json']!=sha(raw[3]):raise ValueError('admission_candidate_manifest')
    elif candidate['files']!=manifest['files']:raise ValueError('admission_candidate_inventory')
    folder=manifest_path.parent
    for name,digest in manifest['files'].items():
        path=(folder/name).resolve()
        if not path.is_relative_to(folder.resolve()) or sha(path.read_bytes())!=digest:raise ValueError('admission_bundle_file')
    for c in runtime['captures']:
        path=(runtime_path.parent/c['file']).resolve()
        if not path.is_relative_to(runtime_path.parent.resolve()) or sha(path.read_bytes())!=c['png_sha256']:raise ValueError('admission_capture_file')
    geometry=candidate.get('geometry',candidate.get('bake_qa'))
    alpha=candidate.get('alpha',candidate.get('shape_qa',{}).get('after'))
    report=evaluate(direct,runtime,geometry,alpha)
    report.update(source_direct_sha256=canonical_sha256(direct),source_runtime_bytes_sha256=sha(raw[1]),source_candidate_sha256=canonical_sha256(candidate))
    return report


def read_admission(saved,direct_path,runtime_path,candidate_path,manifest_path):
    expected=compile_report(direct_path,runtime_path,candidate_path,manifest_path)
    if canonical_sha256(saved)!=canonical_sha256(expected):raise ValueError('admission_reader_mismatch')
    return saved


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('direct','runtime','candidate','manifest','output-dir'):p.add_argument('--'+name,type=Path,required=True)
    args=p.parse_args()
    try:
        report=compile_report(args.direct,args.runtime,args.candidate,args.manifest);digest=canonical_sha256(report)
        args.output_dir.mkdir(parents=True,exist_ok=True);target=args.output_dir/(digest+'.json')
        if target.exists() and canonical_sha256(json.loads(target.read_text()))!=digest:raise ValueError('admission_existing_corrupt')
        target.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        labels={'review_runtime_alpha_loss':'复核：候选区域合成透明度下降','review_pair_alpha_loss':'复核：双附件透明度下降','sampled_no_new_regression':'当前采样未发现新增退化','not_evaluated':'未评估：缺少目标样本','blocked_geometry':'阻塞：几何失败','blocked_boundary_distance':'阻塞：边界增距超限'}
        page='<!doctype html><meta charset="utf-8"><style>body{font:18px system-ui;margin:32px}td,th{padding:12px;border:1px solid #bbb}table{border-collapse:collapse}</style><h1>逐关系候选准入报告</h1><p>仅针对已记录点、原生像素密度。不授予采用权；未发现退化不等于完整接缝通过。</p><table><tr><th>关系</th><th>结论</th><th>样本数</th><th>合成下降</th><th>新增低于8</th></tr>'
        for r in report['relations']:page+='<tr>'+''.join('<td>'+html.escape(str(v))+'</td>' for v in (r['driver']+' → '+r['follower'],labels[r['status']],r['sample_count'],r['all_alpha_loss'],r['new_all_alpha_below8']))+'</tr>'
        (args.output_dir/'index.html').write_text(page+'</table>',encoding='utf-8');print(json.dumps(report));return 0
    except (ValueError,KeyError,TypeError,OSError):
        print(json.dumps(dict(status='blocked',reason_code='seam_admission_evidence_invalid',authority='none')));return 1


if __name__=='__main__':raise SystemExit(main())
