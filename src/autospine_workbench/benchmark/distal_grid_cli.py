"""Run and exactly replay distal support-density experiments independently."""
import argparse
from html import escape
import json
from pathlib import Path

from ..asset.joints.distal_grid import refine, PROFILE
from ..resolved_project import canonical_sha256
from .artifacts import read_input, read_report
from .partition_coverage_cli import build
from .distal_corrective_cli import analyze
from .distal_corrective_view import render_corrective
from .mapping_cli import export_html
from .mesh_storage import read_mesh_report, publish_mesh_report, export_mesh


def compile_report(state, manifest, digest, workspace):
    saved = read_mesh_report(state, manifest['dataset_id'], digest)
    if saved.get('profile') != 'partition-full-alpha-supported-v2':
        raise ValueError('distal_grid_profile_invalid')
    expected, (candidate, composite, images) = build(
        state, manifest, saved['source_mesh_sha256'], workspace, supported=True)
    if canonical_sha256(expected) != digest:
        raise ValueError('distal_grid_mesh_mismatch')
    skeleton = read_report(state, manifest['dataset_id'], 'assisted-skeleton-candidates', saved['source_skeleton_sha256'])
    mesh = refine(saved, candidate, skeleton, images)
    corrective = analyze(mesh, skeleton)
    before = analyze(saved, skeleton)
    comparisons = []
    old = {r['layer_id']: r for r in before['layers']}
    for row in corrective['layers']:
        previous = old[row['layer_id']]
        comparisons.append({'layer_id': row['layer_id'],
            'before_free_vertices': previous['free_vertex_count'], 'after_free_vertices': row['free_vertex_count'],
            'before_min_area': min(s['qa']['min_area_ratio'] for s in previous['samples']),
            'after_min_area': min(s['qa']['min_area_ratio'] for s in row['samples']),
            'before_failed_angles': [s['angle'] for s in previous['samples'] if not s['qa']['passed']],
            'after_failed_angles': [s['angle'] for s in row['samples'] if not s['qa']['passed']]})
    doc = {'schema': 'autospine.distal-grid-experiment/v1', 'profile': PROFILE,
        'authority': 'none', 'production_authorized': False, 'source_mesh_sha256': digest,
        'parameters': {'spacing': 'max(1,floor(shorter_distal_length/4))', 'radius': 'shorter_distal_length',
                       'conformity': 'shared_axis_strips', 'alpha_threshold': 1, 'eligibility_threshold': 8},
        'mesh': mesh, 'corrective': corrective, 'comparisons': comparisons, 'selected_method': None}
    return doc, (candidate, composite)


def read_experiment(state, manifest, digest, *, workspace):
    doc = read_mesh_report(state, manifest['dataset_id'], digest)
    if doc.get('schema') != 'autospine.distal-grid-experiment/v1':
        raise ValueError('distal_grid_schema_invalid')
    expected, _ = compile_report(state, manifest, doc['source_mesh_sha256'], workspace)
    if canonical_sha256(doc) != canonical_sha256(expected):
        raise ValueError('distal_grid_replay_mismatch')
    return doc


def render(candidate, composite, doc):
    html = render_corrective(candidate, composite, doc['corrective'])
    rows = ''.join(f'<tr><td>{escape(r["layer_id"])}</td><td>{r["before_free_vertices"]} → {r["after_free_vertices"]}</td>'
                   f'<td>{r["before_min_area"]:.3f} → {r["after_min_area"]:.3f}</td>'
                   f'<td>{len(r["after_failed_angles"])}/9</td></tr>' for r in doc['comparisons'])
    return html.replace('<main>', '<h2>远端网格加密试验</h2><p>沿关节横纵轴添加支撑线；红线与青线均使用加密网格。'
        '权重规则、修正预算和QA阈值不变。翻转三角形数量受细分影响，比较采用失败角度与面积比。</p>'
        '<table><tr><th>区域</th><th>混合顶点（前→后）</th><th>最小面积比（前→后）</th><th>仍失败角度</th></tr>' + rows + '</table><main>')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-root', type=Path, default=Path(__file__).resolve().parents[3]/'workspace')
    for name in ('manifest', 'workspace', 'mesh', 'html', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        manifest = read_input(args.manifest)
        doc, (candidate, composite) = compile_report(args.state_root, manifest, canonical_sha256(read_input(args.mesh)), args.workspace)
        digest = publish_mesh_report(args.state_root, manifest['dataset_id'], doc)
        export_mesh(args.output, doc)
        export_html(args.html, render(candidate, composite, doc))
        print(json.dumps({'status':'written', 'artifact_sha256':digest, 'comparisons':doc['comparisons']}))
        return 0
    except (OSError, RuntimeError, ValueError, TypeError, KeyError):
        print(json.dumps({'status':'blocked', 'reason_code':'distal_grid_request_failed', 'authority':'none'}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
