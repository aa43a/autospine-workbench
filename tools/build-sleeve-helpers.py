"""Build branched cloth helpers from source-bound garment weights."""
import argparse
from pathlib import Path
import re
from html import escape
from autospine_workbench.project_store import ProjectStore
from autospine_workbench.automation.animated_inputs import load_inputs
from autospine_workbench.benchmark.mesh_storage import read_mesh_report,publish_mesh_report,export_mesh
from autospine_workbench.asset.planning.sleeve_helpers import build
from autospine_workbench.asset.planning.sleeve_helper_review import render
from autospine_workbench.manifest_artifacts import require_safe_token


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--root-transition',action='store_true')
    p.add_argument('--state-root',type=Path,default=Path('workspace'));p.add_argument('--workspace',type=Path,default=Path('..'))
    p.add_argument('projects',nargs='+');a=p.parse_args();store=ProjectStore(a.workspace,a.state_root);links=[]
    for project in a.projects:
        require_safe_token(project,'Project')
        page=(a.input/project/'index.html').read_text(encoding='utf-8');sha=re.search(r'href="([a-f0-9]{64})\.json"',page).group(1)
        source=read_mesh_report(a.state_root,'project-component-partitions',sha)
        if source['project_id']!=project:raise ValueError('cloth_project_mismatch')
        with load_inputs(store,project) as inputs:
            doc=build(source,inputs.skeleton,a.root_transition);inputs.assert_current()
            digest=publish_mesh_report(a.state_root,'project-component-partitions',doc)
            checked=read_mesh_report(a.state_root,'project-component-partitions',digest)
            if checked!=doc:raise ValueError('cloth_helper_readback')
            out=a.output/project;out.mkdir(parents=True,exist_ok=True);export_mesh(out/f'{digest}.json',checked)
            (out/'index.html').write_text(render(checked).replace('<main>',f'<a href="{digest}.json">完整工件</a><main>'),encoding='utf-8')
            for row in doc['records']:
                if 'tracks' in row:print(project,row['layer_id'],[(t['bone_id'],t['failed_ticks']) for t in row['tracks']],flush=True)
            links.append(f'<li><a href="{escape(project)}/index.html">{escape(project)}</a></li>')
    (a.output/'index.html').write_text('<meta charset="utf-8"><h1>垂布辅助骨候选</h1><ul>'+''.join(links)+'</ul><p>袖口/共享边界仍须验证，未正式采用。</p>',encoding='utf-8')


if __name__=='__main__':main()
