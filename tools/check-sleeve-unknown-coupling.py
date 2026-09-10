"""Source-bound ownership/weight diagnosis with setup-space localization."""
import argparse
import base64
from html import escape
from pathlib import Path
from autospine_workbench.asset.planning.sleeve_unknown_coupling import analyze
from autospine_workbench.asset.planning.sleeve_regions import validate
from autospine_workbench.benchmark.artifacts import read_input,publish_report,read_report,export_document
from autospine_workbench.benchmark.mesh_storage import read_mesh_report
from autospine_workbench.automation.animated_inputs import load_inputs
from autospine_workbench.project_store import ProjectStore
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.safe_input_files import read_real_file,strict_json_object


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True);p.add_argument('--draft',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--state-root',type=Path,default=Path('workspace'))
    p.add_argument('--workspace',type=Path,default=Path('..'));a=p.parse_args()
    source=read_mesh_report(a.state_root,'project-component-partitions',a.source.stem)
    if source!=strict_json_object(read_real_file(a.source,128<<20,'sleeve source'),'sleeve source'):raise ValueError('sleeve_coupling_source')
    draft=read_input(a.draft);candidate=read_mesh_report(a.state_root,'project-component-partitions',draft['candidate_sha256'])
    validate(draft,candidate)
    ancestor=source
    for _ in range(16):
        if 'draft_sha256' in ancestor:break
        ancestor=read_mesh_report(a.state_root,'project-component-partitions',ancestor['source_sha256'])
    if ancestor.get('draft_sha256')!=canonical_sha256(draft):raise ValueError('sleeve_coupling_draft_source')
    if source['project_id']!=draft['project_id']:raise ValueError('sleeve_coupling_project')
    labels={(r['layer_id'],r['component_id']):r for r in draft['records']}
    meshes={(r['layer_id'],r['component_id']):r for r in candidate['records']}
    store=ProjectStore(a.workspace,a.state_root);records=[];views=[]
    with load_inputs(store,source['project_id']) as inputs:
        if canonical_sha256(inputs.skeleton)!=source['skeleton_sha256']:raise ValueError('sleeve_coupling_skeleton')
        for row in source['records']:
            if 'weights' not in row:continue
            key=row['layer_id'],row['component_id'];mesh=meshes[key]
            if row['triangles']!=mesh['triangles'] or row['setup_vertices']!=mesh['vertices_xy']:raise ValueError('sleeve_coupling_geometry')
            bad={i for t in row['tracks'] for q in t['qa'] for i in q['bad_triangles']}
            diagnosis=analyze(row['triangles'],labels[key]['assignments'],row['weights'],mesh['bone_ids'][2],bad)
            records.append(dict(layer_id=key[0],component_id=key[1],**diagnosis))
            layer=next(l for l in inputs.candidate['layers'] if l['layer_id']==key[0]);x,y,w,h=layer['bbox']
            image=base64.b64encode(inputs.images[key[0]]).decode()
            shapes=[]
            for i in sorted(bad|set(diagnosis['unknown_triangles'])):
                pts=' '.join(','.join(map(str,row['setup_vertices'][v])) for v in row['triangles'][i])
                color='#ffb000' if i in diagnosis['unknown_triangles'] else '#ff4455'
                shapes.append(f'<polygon points="{pts}" fill="{color}" fill-opacity=".4" stroke="{color}" stroke-width="1"><title>triangle {i}</title></polygon>')
            views.append(f'<h2>{escape(key[0])}</h2><p>橙色：与手驱动耦合的不确定三角形 {diagnosis["unknown_triangles"]}；红色：动作中失败的三角形投影到setup。共享顶点影响是诊断证据，不是因果证明。</p><svg viewBox="{x} {y} {w} {h}" style="height:75vh;max-width:100%"><image href="data:image/png;base64,{image}" x="{x}" y="{y}" width="{w}" height="{h}"/>'+''.join(shapes)+'</svg>')
        inputs.assert_current()
    report=dict(schema='autospine.sleeve-unknown-coupling/v1',authority='none',production_authorized=False,
        project_id=source['project_id'],source_sha256=canonical_sha256(source),draft_sha256=canonical_sha256(draft),records=records)
    sha=publish_report(a.state_root,'project-component-partitions','unknown-coupling-v1',report)
    checked=read_report(a.state_root,'project-component-partitions','unknown-coupling-v1',sha)
    a.output.mkdir(parents=True,exist_ok=True);export_document(a.output/(sha+'.json'),checked)
    (a.output/'index.html').write_text('<!doctype html><meta charset="utf-8"><style>body{background:#18232f;color:white;font:18px system-ui;margin:24px}svg{background:#384552}a{color:#8df}</style><h1>未知归属与手驱动耦合</h1><p>不修改标注、权重或网格，不自动采用。</p>'+''.join(views)+f'<p><a href="{sha}.json">来源与诊断</a></p>',encoding='utf-8')
    print(sha)


if __name__=='__main__':main()
