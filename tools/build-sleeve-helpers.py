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
    p.add_argument('--multi-anchor',action='store_true',help='Test cloth-only corrective keys with fixed interface vertices')
    p.add_argument('--motion-envelope',action='store_true',help='Validate fixed R3-S individual and combined motion range')
    p.add_argument('--connection-domain',action='store_true',help='Allow role-bounded garment connection support')
    p.add_argument('--baseline-envelope',type=Path)
    p.add_argument('--interface-root',action='store_true',help='Read helper input and test semantic attachment roots')
    p.add_argument('--state-root',type=Path,default=Path('workspace'));p.add_argument('--workspace',type=Path,default=Path('..'))
    p.add_argument('projects',nargs='+');a=p.parse_args();store=ProjectStore(a.workspace,a.state_root);links=[]
    if sum([a.root_transition,a.interface_root,a.multi_anchor,a.motion_envelope])>1:p.error('root modes are mutually exclusive')
    if a.connection_domain and not a.motion_envelope:p.error('connection-domain requires motion-envelope')
    if a.connection_domain and not a.baseline_envelope:p.error('connection-domain requires baseline-envelope')
    for project in a.projects:
        require_safe_token(project,'Project')
        page=(a.input/project/'index.html').read_text(encoding='utf-8');sha=re.search(r'href="([a-f0-9]{64})\.json"',page).group(1)
        source=read_mesh_report(a.state_root,'project-component-partitions',sha)
        if source['project_id']!=project:raise ValueError('cloth_project_mismatch')
        with load_inputs(store,project) as inputs:
            if a.motion_envelope:
                from autospine_workbench.asset.planning.sleeve_motion_envelope import build as envelope_build
                domains=None
                if a.connection_domain:
                    from autospine_workbench.asset.planning.sleeve_connection_domain import prepare
                    garment=source
                    for _ in range(8):
                        if garment['schema']=='autospine.sleeve-weights/v1':break
                        garment=read_mesh_report(a.state_root,'project-component-partitions',garment['source_sha256'])
                    draft=read_mesh_report(a.state_root,'project-component-partitions',garment['draft_sha256'])
                    domains=prepare(source,garment,draft)
                doc=envelope_build(source,inputs.skeleton,domains)
                if a.connection_domain:
                    from autospine_workbench.asset.planning.sleeve_connection_domain import retain
                    prior=(a.baseline_envelope/project/'index.html').read_text(encoding='utf-8')
                    prior_sha=re.search(r'href="([a-f0-9]{64})\.json"',prior).group(1)
                    doc=retain(doc,read_mesh_report(a.state_root,'project-component-partitions',prior_sha))
            elif a.multi_anchor:
                from autospine_workbench.asset.planning.cloth_anchor_correction import build as anchor_build
                doc=anchor_build(source,inputs.skeleton)
            elif a.interface_root:
                from autospine_workbench.asset.planning.cloth_interface_root import build as interface_build
                def read(digest):return read_mesh_report(a.state_root,'project-component-partitions',digest)
                garment=read(source['source_sha256']);candidate=read(garment['candidate_sha256']);draft=read(garment['draft_sha256'])
                doc=interface_build(source,garment,candidate,draft,inputs.skeleton)
            else:doc=build(source,inputs.skeleton,a.root_transition)
            inputs.assert_current()
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
