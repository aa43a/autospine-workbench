"""Export axial-band trials from exact guarded candidates without adopting results."""
import argparse
from html import escape
from pathlib import Path
import re
from autospine_workbench.project_store import ProjectStore
from autospine_workbench.automation.animated_inputs import load_inputs
from autospine_workbench.benchmark.mesh_storage import read_mesh_report, publish_mesh_report, export_mesh
from autospine_workbench.asset.planning.component_axial_correction import build
from autospine_workbench.asset.planning.component_mesh_review import render
from autospine_workbench.asset.planning.component_temporal_qa import passed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--state-root', type=Path, default=Path('workspace'))
    parser.add_argument('--workspace', type=Path, default=Path('..'))
    parser.add_argument('projects', nargs='+')
    args = parser.parse_args(); store = ProjectStore(args.workspace, args.state_root); summary = []
    from autospine_workbench.manifest_artifacts import require_safe_token
    for project in args.projects:
        require_safe_token(project, 'Project')
        page = (args.input/project/'index.html').read_text(encoding='utf-8')
        sha = re.search(r'href="([a-f0-9]{64})\.json"', page).group(1)
        source = read_mesh_report(args.state_root, 'project-component-partitions', sha)
        if source['project_id'] != project: raise ValueError('axial_project_mismatch')
        with load_inputs(store, project) as inputs:
            document = build(source, inputs.skeleton); inputs.assert_current()
            digest = publish_mesh_report(args.state_root, 'project-component-partitions', document)
            checked = read_mesh_report(args.state_root, 'project-component-partitions', digest)
            if checked != document: raise ValueError('axial_readback_mismatch')
            output = args.output/project; output.mkdir(parents=True, exist_ok=True)
            export_mesh(output/f'{digest}.json', checked)
            before = sum(not passed(q) for r in checked['evidence'] for q in r['before'])
            after = sum(not passed(q) for r in checked['evidence'] for q in r['after'])
            selected = sum(t['selected'] for r in checked['evidence'] for t in r['trials'])
            details = '<ul>'+''.join(f'<li>{escape(r["layer_id"])} / {escape(r["bone_id"])}：'
                + '; '.join(escape(t['key_id'])+': '+escape(', '.join(t['reason_codes'])) for t in r['trials'])+'</li>' for r in checked['evidence'])+'</ul>'
            intro = f'<h2>末端轴向带修正</h2><p>末端轨道失败 {before} → {after}；{selected} 个候选关键姿态保留收益。位移预算不变，尚非正式采用。</p>{details}<a href="{digest}.json">完整数据</a>'
            overrides = {(r['layer_id'], r['component_id']): r['poses'] for r in checked['rows']}
            (output/'index.html').write_text(render(checked, inputs.skeleton, overrides, fk=True).replace('<main>', intro+'<main>'), encoding='utf-8')
            summary.append(f'<tr><td><a href="{escape(project)}/index.html">{escape(project)}</a></td><td>{before} → {after}</td><td>{selected}</td></tr>')
            print(project, digest, before, after, selected, flush=True)
    page = '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>轴向修正对照</title><style>body{background:#17212d;color:white;font:18px system-ui;margin:30px}a{color:#9df}td,th{padding:16px}</style><h1>轴向带修正 · 固定规则跨角色对照</h1><p>只统计手/足末端轨道，每条129点；其他轨道保持不变。权重、UV、拓扑和原始位移预算不变。新增回归则保留原候选，未修改默认流程。</p>'
    page += '<table><tr><th>角色/拖动播放</th><th>末端失败采样</th><th>保留收益的关键姿态</th></tr>'+''.join(summary)+'</table><p>仍有失败；未完成纹理、接缝或官方Runtime验收。</p></html>'
    (args.output/'index.html').write_text(page, encoding='utf-8')


if __name__ == '__main__': main()
