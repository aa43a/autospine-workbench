"""Replay exact prior comparisons and export whole-region fallback candidates."""
import argparse
from pathlib import Path
from html import escape
from autospine_workbench.benchmark.artifacts import read_report
from autospine_workbench.benchmark.mesh_storage import read_mesh_report, publish_mesh_report, export_mesh
from autospine_workbench.project_store import ProjectStore
from autospine_workbench.automation.animated_inputs import load_inputs
from autospine_workbench.asset.planning.component_distal_guard import build
from autospine_workbench.asset.planning.component_mesh_review import render
from autospine_workbench.asset.planning.component_temporal_qa import passed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--comparison', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--state-root', type=Path, default=Path('workspace'))
    parser.add_argument('--workspace', type=Path, default=Path('..'))
    args = parser.parse_args(); store = ProjectStore(args.workspace, args.state_root)
    comparison = read_report(args.state_root, 'project-component-partitions', 'parent-distal-comparison-v1', args.comparison)
    def read(sha): return read_mesh_report(args.state_root, 'project-component-partitions', sha)
    summary = []
    for case in comparison['cases']:
        oldkeys, newkeys = read(case['old_keys_sha256']), read(case['trial_keys_sha256'])
        old, trial = read(oldkeys['source_sha256']), read(newkeys['source_sha256'])
        project = case['project_id']
        with load_inputs(store, project) as inputs:
            result = build(old, trial, oldkeys, newkeys, inputs.skeleton)
            inputs.assert_current(); digest = publish_mesh_report(args.state_root, 'project-component-partitions', result)
            checked = read(digest)
            if checked != result: raise ValueError('distal_guard_readback_mismatch')
            output = args.output/project; output.mkdir(parents=True, exist_ok=True)
            export_mesh(output/f'{digest}.json', checked)
            detail = []; before = 0; after = 0; selected = 0
            for region in checked['evidence']:
                chosen = region['selected_trial']; selected += chosen
                a = sum(not passed(t) for c in region['comparisons'] for t in c['before'])
                b = sum(not passed(t) for c in region['comparisons'] for t in c['after']) if chosen else a
                before += a; after += b
                detail.append(f'<li>{escape(region["layer_id"])} / {escape(region["component_id"])}：'
                              f'{"新候选" if chosen else "保留旧候选"}，{a} → {b}；{escape(", ".join(region["reason_codes"]))}</li>')
            intro = '<h2>整区域回退 · 129点FK检查</h2><p>权重与修正成套选择，不按帧切换。保留旧候选不表示旧候选已通过。</p>'
            intro += '<ul>'+''.join(detail)+f'</ul><a href="{digest}.json">完整数据与来源</a>'
            overrides = {(r['layer_id'], r['component_id']): r['poses'] for r in checked['rows']}
            page = render(checked, inputs.skeleton, overrides, fk=True).replace('<main>', intro+'<main>')
            (output/'index.html').write_text(page, encoding='utf-8')
            summary.append(f'<tr><td><a href="{escape(project)}/index.html">{escape(project)}</a></td><td>{selected}</td><td>{before} → {after}</td></tr>')
            print(project, digest, before, after, selected, flush=True)
    page = '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>区域回退对照</title><style>body{background:#17212d;color:white;font:18px system-ui;margin:30px}a{color:#9df}td,th{padding:16px}</style><h1>同一规则 · 逐区域收益与回退</h1>'
    page += '<p>129个采样点/关节轨道；新增失败、翻转、面积坏三角形数量或超限拉伸恶化时，整个区域保留旧权重和旧修正。未按角色设阈值。采样不证明连续时间安全。</p>'
    page += '<table><tr><th>角色/拖动播放</th><th>使用新候选的区域数</th><th>密集采样失败：旧→回退组合</th></tr>'+''.join(summary)+'</table>'
    page += '<p>此处是候选组合。尚有失败，默认流程未更改；纹理、接缝和官方Runtime均未验收。</p></html>'
    (args.output/'index.html').write_text(page, encoding='utf-8')


if __name__ == '__main__': main()
