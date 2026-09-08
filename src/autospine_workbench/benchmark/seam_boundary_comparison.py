"""Exact reference probe replay plus actual same-position Runtime comparison."""
import argparse
import hashlib
import html
import json
from pathlib import Path

from ..resolved_project import canonical_sha256
from ..targets.spine43.seam_admission import evaluate
from .seam_boundary_probes import compile_report as probes
from .seam_candidate_hub import bundle_bytes


def compile_report(reference_path, reference_manifest, probe_path, runtime_path, candidate_path, manifest_path):
    probe = json.loads(probe_path.read_bytes())
    expected = probes(reference_path, reference_manifest, probe['relations'][0]['follower'])
    if canonical_sha256(probe) != canonical_sha256(expected):
        raise ValueError('boundary_probe_replay')
    runtime_raw = runtime_path.read_bytes()
    runtime = json.loads(runtime_raw)
    candidate = json.loads(candidate_path.read_bytes())
    sha = lambda raw: hashlib.sha256(raw).hexdigest()
    if runtime['schema'] != 'autospine.seam-local-runtime/v3' or runtime['probe_report_sha256'] != sha(probe_path.read_bytes()):
        raise ValueError('boundary_runtime_probe')
    if runtime['bundle_manifest_sha256']['before'] != probe['reference_manifest_sha256']:
        raise ValueError('boundary_runtime_reference')
    if runtime['bundle_manifest_sha256']['after'] != sha(manifest_path.read_bytes()):
        raise ValueError('boundary_runtime_candidate')
    if candidate['files']['preview-manifest.json'] != sha(manifest_path.read_bytes()):
        raise ValueError('boundary_candidate_manifest')
    bundle_bytes(manifest_path.parent, candidate['files'])
    bundle_bytes(runtime_path.parent, {c['file']: c['png_sha256'] for c in runtime['captures']})
    report = evaluate(probe, runtime, candidate['geometry'], candidate['alpha'])
    report.update(source_probe_sha256=canonical_sha256(probe), source_runtime_bytes_sha256=sha(runtime_raw),
                  source_candidate_sha256=canonical_sha256(candidate))
    report['samples'] = []
    captures = {(c['sample_index'], c['variant'], c['mode']): c for c in runtime['captures']
                if c['scale'] == 1 and c['atlas'] == 'shared'}
    for i, sample in enumerate(probe['relations'][0]['samples']):
        before = captures[i, 'before', 'all']['rgba'][0][3]
        after = captures[i, 'after', 'all']['rgba'][0][3]
        report['samples'].append(dict(sample, before_alpha=before, after_alpha=after,
                                     alpha_loss=before-after, new_below8=before>=8 and after<8))
    report['baseline_below8'] = sum(s['before_alpha'] < 8 for s in report['samples'])
    report['candidate_below8'] = sum(s['after_alpha'] < 8 for s in report['samples'])
    return report


def read_comparison(saved, *sources):
    if canonical_sha256(saved) != canonical_sha256(compile_report(*sources)):
        raise ValueError('boundary_comparison_replay')
    return saved


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    keys = ('reference', 'reference-manifest', 'probe', 'runtime', 'candidate', 'manifest', 'output-dir')
    for key in keys:
        parser.add_argument('--'+key, required=True, type=Path)
    args = parser.parse_args()
    report = compile_report(*(getattr(args, k.replace('-', '_')) for k in keys[:-1]))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    target = args.output_dir / (canonical_sha256(report)+'.json')
    if target.exists() and json.loads(target.read_bytes()) != report:
        raise ValueError('boundary_comparison_existing_corrupt')
    target.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    view = '<!doctype html><meta charset="utf-8"><style>body{font:17px system-ui;margin:30px}td,th{padding:9px;border-bottom:1px solid #ddd}table{border-collapse:collapse}</style><h1>Alice 右侧独立边界采样</h1><p>原动画决定采样位置：3处边界 × 61个时刻；原生像素密度、共享Atlas。不是疑似裂缝集合，也不是完整接缝验收。</p>'
    row = report['relations'][0]
    view += '<p>合成alpha下降超过1：'+str(row['all_alpha_loss'])+'；新增低于8：'+str(row['new_all_alpha_below8'])+'；最大下降：'+str(row['max_all_alpha_loss'])+'。</p>'
    view += '<p>原／候选低于8的目标：'+str(report['baseline_below8'])+'／'+str(report['candidate_below8'])+'。候选待复核，未授予采用权。</p><table><tr><th>帧</th><th>原边界配对</th><th>原alpha</th><th>候选alpha</th><th>下降</th><th>局部图片</th></tr>'
    for s in sorted(report['samples'], key=lambda s: -s['alpha_loss']):
        i = report['samples'].index(s)
        links = ' ／ '.join('<a href="'+html.escape((args.runtime.parent/f'{v}-{i}-1-shared-all.png').resolve().as_uri(), quote=True)+'">'+label+'</a>' for v,label in (('before','原'),('after','候选')))
        view += '<tr>'+''.join('<td>'+html.escape(str(s[k]))+'</td>' for k in ('frame','pair_index','before_alpha','after_alpha','alpha_loss'))+'<td>'+links+'</td></tr>'
    (args.output_dir/'index.html').write_text(view+'</table>', encoding='utf-8')
    print(json.dumps(dict(relations=report['relations'], baseline_below8=report['baseline_below8'], candidate_below8=report['candidate_below8'])))


if __name__ == '__main__':
    main()
