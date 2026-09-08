"""Compare three fixed alpha-width policies with an exact full-alpha baseline."""
import argparse
import json
from pathlib import Path
from html import escape

from ..asset.joints.distal_width import measure, reweight
from ..asset.joints.distal_corrective import prepare, sample, ANGLES
from ..asset.joints.partition_mesh_qa import evaluate
from ..png_rgba import decode_rgba_png
from ..resolved_project import canonical_sha256
from .artifacts import read_input, read_report
from .partition_coverage_cli import build
from .mesh_storage import read_mesh_report, publish_mesh_report, export_mesh
from .mapping_cli import export_html
from .distal_corrective_view import render_corrective


def compile_report(state, manifest, digest, workspace):
    mesh = read_mesh_report(state, manifest['dataset_id'], digest)
    if mesh.get('profile') != 'partition-full-alpha-supported-v2':
        raise ValueError('distal_width_source_invalid')
    expected, (candidate, composite, images) = build(state, manifest, mesh['source_mesh_sha256'], workspace, supported=True)
    if canonical_sha256(expected) != digest: raise ValueError('distal_width_source_mismatch')
    skeleton = read_report(state, manifest['dataset_id'], 'assisted-skeleton-candidates', mesh['source_skeleton_sha256'])
    bones = {b['id']:b for b in skeleton['bones']}
    sources = {r['layer_id']:r for r in candidate['layers']}
    rows = []; views = []
    for original in mesh['layers']:
        if len(original['bone_ids']) != 3: continue
        chain = [bones[b] for b in original['bone_ids']]
        evidence = measure(decode_rgba_png(images[original['layer_id']]), sources[original['layer_id']]['bbox'][:2], chain)
        baseline = prepare(original, chain)
        old = [sample(baseline,a)['qa'] for a in ANGLES]
        trials = []
        for factor in (1,2,4):
            row, policy = reweight(original, chain, evidence, factor)
            context = prepare(row,chain); samples = [sample(context,a) for a in ANGLES]
            qa = evaluate(row['vertices_xy'],row['triangles'],row['weights'],chain)
            trials.append({'policy':policy, 'weights':row['weights'], 'lbs_qa':qa,
                'corrective_qa':[dict(s['qa'],angle=s['angle']) for s in samples],
                'status':'candidate_requires_review' if qa['passed'] and all(s['qa']['passed'] for s in samples) else 'blocked'})
            if factor == 2:
                views.append({'layer_id':row['layer_id'], 'joint_id':chain[2]['id'], 'triangles':row['triangles'],
                    'free_vertex_count':sum(context['free']), 'projection_budget_px':context['budget'],
                    'status':trials[-1]['status'], 'samples':samples})
        rows.append({'layer_id':original['layer_id'], 'evidence':evidence, 'baseline_corrective_qa':old, 'trials':trials})
    doc = {'schema':'autospine.distal-width-experiment/v1', 'profile':'alpha-transverse-distal-width-v1',
        'authority':'none', 'production_authorized':False, 'source_mesh_sha256':digest,
        'source_skeleton_sha256':mesh['source_skeleton_sha256'], 'selected_method':None,
        'parameters':{'factors':[1,2,4], 'alpha_threshold':8, 'slab':'shorter_distal_length', 'cap_fraction':.45}, 'layers':rows}
    return doc, (candidate,composite,{'layers':views})


def read_experiment(state, manifest, digest, *, workspace):
    doc = read_mesh_report(state,manifest['dataset_id'],digest)
    expected,_ = compile_report(state,manifest,doc['source_mesh_sha256'],workspace)
    if canonical_sha256(expected)!=canonical_sha256(doc): raise ValueError('distal_width_replay_mismatch')
    return doc


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-root',type=Path,default=Path(__file__).resolve().parents[3]/'workspace')
    for name in ('manifest','workspace','mesh','html','output'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        doc,(candidate,composite,view)=compile_report(args.state_root,read_input(args.manifest),canonical_sha256(read_input(args.mesh)),args.workspace)
        digest=publish_mesh_report(args.state_root,read_input(args.manifest)['dataset_id'],doc)
        export_mesh(args.output,doc)
        rows=[]
        for row in doc['layers']:
            for trial in row['trials']:
                q=trial['corrective_qa'];p=trial['policy']
                rows.append(f'<tr><td>{escape(row["layer_id"])}</td><td>{p["factor"]}</td><td>{p["halfwidth_px"]:.2f}</td>'
                    f'<td>{min(x["min_area_ratio"] for x in q):.3f}</td><td>{sum(not x["passed"] for x in q)}/9</td><td>{trial["status"]}</td></tr>')
        html=render_corrective(candidate,composite,view).replace('<main>',
            '<h2>Alpha横向宽度试验</h2><p>原网格不加密。下方线框固定展示系数2，仅供诊断，未选择或采用。表中为三种预设系数。</p>'
            '<table><tr><th>区域</th><th>系数</th><th>半宽px</th><th>最小面积比</th><th>失败角度</th><th>总状态</th></tr>'+''.join(rows)+'</table><main>')
        export_html(args.html,html)
        print(json.dumps({'status':'written','artifact_sha256':digest,'trials':[{'layer':r['layer_id'],'status':[t['status'] for t in r['trials']]} for r in doc['layers']]}))
        return 0
    except (ValueError,TypeError,KeyError,OSError,RuntimeError):
        print(json.dumps({'status':'blocked','reason_code':'distal_width_request_failed','authority':'none'}));return 1


if __name__=='__main__':raise SystemExit(main())
