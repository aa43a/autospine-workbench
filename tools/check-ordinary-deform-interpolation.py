"""Replay quarter-tick ordinary deformation checks and export readable evidence."""
import argparse
from html import escape
from pathlib import Path
from autospine_workbench.project_store import ProjectStore
from autospine_workbench.automation.animated_inputs import load_inputs
from autospine_workbench.asset.planning.ordinary_deform_interpolation import build
from autospine_workbench.benchmark.mesh_storage import read_mesh_report, publish_mesh_report, export_mesh
from autospine_workbench.manifest_artifacts import require_safe_token


def render(report):
    rows = []
    for region in report['records']:
        label = escape(region['layer_id']+' / '+region['component_id'])
        for t in region['tracks']:
            rows.append(f'<tr><td>{label}</td><td>{escape(t["bone_id"])}</td><td>{len(t["failed_samples"])}/513</td>'
                        f'<td>{len(t["failed_between_keys"])}</td><td>{len(t["new_failed_between_keys"])}</td>'
                        f'<td>{t["max_cyclic_delta_second_difference_normalized"]:.6f}</td></tr>')
        if not region['tracks']: rows.append(f'<tr><td>{label}</td><td colspan="5">无可用轨道，保留阻塞</td></tr>')
    return ('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>普通袖加密插值检查</title>'
            '<style>body{font:16px system-ui;background:#142331;color:#e4f0ff;padding:24px}td,th{padding:12px;border:1px solid #597080}table{border-collapse:collapse}p{max-width:1000px;overflow-wrap:anywhere}</style>'
            '<h1>普通袖加密插值检查</h1><p>每轨513个时刻：解析骨骼动作 + 画布世界坐标修正的线性插值。'
            '不是Spine局部deform插值，也不是连续时间数学证明。</p>'
            '<p>周期二阶差分按网格中位边长归一，仅作抖动诊断；尚未以该指标批准视觉质量。</p>'
            f'<p>来源：{escape(report["deform_sha256"])}</p>'
            '<table><thead><tr><th>区域</th><th>轨道</th><th>失败样本</th><th>关键帧间失败</th><th>相对原FK新增失败</th><th>归一二阶差分峰值</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table><p>所有结果保持候选，不产生采用或发布权。</p></html>')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project'); parser.add_argument('--deform', required=True)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--state-root', default=Path('workspace'), type=Path)
    parser.add_argument('--workspace', default=Path('..'), type=Path)
    args = parser.parse_args(); require_safe_token(args.project, 'project')
    read = lambda sha: read_mesh_report(args.state_root, 'project-component-partitions', sha)
    deform = read(args.deform)
    if deform['project_id'] != args.project: raise ValueError('ordinary_interpolation_project_mismatch')
    repair, source, draft = [read(deform[k]) for k in ('repair_sha256','source_sha256','draft_sha256')]
    with load_inputs(ProjectStore(args.workspace.resolve(), args.state_root.resolve()), args.project) as inputs:
        report = build(deform, repair=repair, source=source, draft=draft, skeleton=inputs.skeleton)
        inputs.assert_current()
        sha = publish_mesh_report(args.state_root, 'project-component-partitions', report)
        if read(sha) != report: raise ValueError('ordinary_interpolation_readback_mismatch')
        args.output.mkdir(parents=True, exist_ok=True)
        export_mesh(args.output/(sha+'.json'), report)
        (args.output/'index.html').write_text(render(report), encoding='utf-8')
        print(sha)


if __name__ == '__main__': main()
