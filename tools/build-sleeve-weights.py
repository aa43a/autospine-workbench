"""Compile and visualize garment weight candidates from archived ownership drafts."""
import argparse
from pathlib import Path
from html import escape
from autospine_workbench.project_store import ProjectStore
from autospine_workbench.automation.animated_inputs import load_inputs
from autospine_workbench.benchmark.mesh_storage import read_mesh_report,publish_mesh_report,export_mesh
from autospine_workbench.benchmark.artifacts import read_input
from autospine_workbench.asset.planning.sleeve_weights import build
from autospine_workbench.asset.planning.component_mesh_review import render
from autospine_workbench.asset.planning.component_temporal_qa import passed
from autospine_workbench.manifest_artifacts import require_safe_token


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--boundary-transition',action='store_true',help='Probe guarded graph-based cuff transitions')
    p.add_argument('--state-root',type=Path,default=Path('workspace'));p.add_argument('--workspace',type=Path,default=Path('..'))
    p.add_argument('projects',nargs='+');a=p.parse_args();store=ProjectStore(a.workspace,a.state_root);links=[]
    def read(sha):return read_mesh_report(a.state_root,'project-component-partitions',sha)
    for project in a.projects:
        require_safe_token(project,'Project');draft=read_input(a.input/project/'draft.json')
        candidate=read(draft['candidate_sha256']);source=read(candidate['source_sha256'])
        if source['project_id']!=project:raise ValueError('sleeve_weight_project_mismatch')
        with load_inputs(store,project) as inputs:
            doc=build(source,candidate,draft,inputs.skeleton,a.boundary_transition);inputs.assert_current()
            sha=publish_mesh_report(a.state_root,'project-component-partitions',doc);checked=read(sha)
            if checked!=doc:raise ValueError('sleeve_weight_readback')
            out=a.output/project;out.mkdir(parents=True,exist_ok=True);export_mesh(out/f'{sha}.json',checked)
            detail=[]
            for r in checked['evidence']:
                before=sum(not passed(q) for c in r['comparisons'] for q in c['before'])
                after=sum(not passed(q) for c in r['comparisons'] for q in c['after'])
                detail.append(f'<li>{escape(r["layer_id"])}：{len(r["changed_vertices"])}顶点移除手骨影响，混合边界{len(r["mixed_boundary_vertices"])}顶点；原始FK失败{before}→{after}；{escape(", ".join(r["reason_codes"]))}</li>')
                print(project,r['layer_id'],len(r['changed_vertices']),before,after,flush=True)
                if 'boundary_transition' in r:
                    b=r['boundary_transition'];detail.append(f'<li>边界过渡：{"保留新候选" if b["selected"] else "回退到内部权重候选"}；{escape(", ".join(b["reason_codes"]))}</li>')
            intro='<h2>服装权重候选</h2><p>袖布和垂布内部去除手骨影响并转给前臂，保留上臂权重；这只是垂布主驱动，尚无辅助骨或次级运动。手、袖口、不确定和混合边界暂留旧权重。旧修正未复用；下方为新权重原始FK，不可与上一版修正后失败计数混比。</p>'
            intro+='<ul>'+''.join(detail)+f'</ul><a href="{sha}.json">完整来源与QA</a> · <a href="baseline.html">同条件旧权重FK</a>'
            if a.boundary_transition:intro='<p>正在检查图邻接边界候选：手/不确定顶点固定，袖口允许渐变；密集QA有回归则整区域回退。仍未实现接触约束或辅助链。</p>'+intro
            (out/'index.html').write_text(render(checked,inputs.skeleton,fk=True).replace('<main>',intro+'<main>'),encoding='utf-8')
            (out/'baseline.html').write_text(render(source,inputs.skeleton,fk=True),encoding='utf-8')
            links.append(f'<li><a href="{escape(project)}/index.html">{escape(project)}</a></li>')
    (a.output/'index.html').write_text('<meta charset="utf-8"><h1>袖布权重候选</h1><p>仍有边界/袖口/垂布缺项，未正式采用。</p><ul>'+''.join(links)+'</ul>',encoding='utf-8')


if __name__=='__main__':main()
