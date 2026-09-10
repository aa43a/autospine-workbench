"""Create triangle ownership review pages and validate returned source-bound drafts."""
import argparse
from pathlib import Path
import re
from html import escape
from autospine_workbench.project_store import ProjectStore
from autospine_workbench.automation.animated_inputs import load_inputs
from autospine_workbench.benchmark.mesh_storage import read_mesh_report, publish_mesh_report, export_mesh
from autospine_workbench.benchmark.artifacts import read_input
from autospine_workbench.asset.planning.sleeve_regions import build, template, validate
from autospine_workbench.asset.planning.sleeve_region_review import render
from autospine_workbench.manifest_artifacts import require_safe_token


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--draft',type=Path)
    parser.add_argument('--state-root',type=Path,default=Path('workspace'))
    parser.add_argument('--workspace',type=Path,default=Path('..'))
    parser.add_argument('projects',nargs='+');args=parser.parse_args()
    if args.draft and len(args.projects)!=1:parser.error('--draft requires one project')
    store=ProjectStore(args.workspace,args.state_root);links=[]
    for project in args.projects:
        require_safe_token(project,'Project')
        page=(args.input/project/'index.html').read_text(encoding='utf-8')
        sha=re.search(r'href="([a-f0-9]{64})\.json"',page).group(1)
        source=read_mesh_report(args.state_root,'project-component-partitions',sha)
        if source['project_id']!=project:raise ValueError('sleeve_project_mismatch')
        with load_inputs(store,project) as inputs:
            candidate=build(source,inputs.skeleton);draft=template(candidate)
            if args.draft:draft=validate(read_input(args.draft),candidate)
            output=args.output/project;output.mkdir(parents=True,exist_ok=True)
            inputs.assert_current()
            for doc in (candidate,draft):
                digest=publish_mesh_report(args.state_root,'project-component-partitions',doc)
                checked=read_mesh_report(args.state_root,'project-component-partitions',digest)
                if checked!=doc:raise ValueError('sleeve_readback_mismatch')
                export_mesh(output/f'{digest}.json',checked)
            export_mesh(output/'draft.json',draft)
            (output/'index.html').write_text(render(candidate,draft,inputs,source),encoding='utf-8')
            count=sum(len(r['triangles']) for r in candidate['records'])
            links.append(f'<li><a href="{escape(project)}/index.html">{escape(project)} · {count}三角形</a></li>')
            print(project,count,flush=True)
    (args.output/'index.html').write_text('<!doctype html><meta charset="utf-8"><h1>袖子归属草稿</h1><p>几何建议不是人体/服装语义真值。下载草稿后可载入或由CLI校验封存，不产生绑定授权。</p><ul>'+''.join(links)+'</ul>',encoding='utf-8')


if __name__=='__main__':main()
