"""Exact source replay and independent, non-adopted distal corrective samples."""
from pathlib import Path
from ..resolved_project import canonical_sha256
from ..asset.joints.distal_corrective import prepare,sample,ANGLES
from .artifacts import read_input,read_report
from .mesh_storage import read_mesh_report
from .partition_coverage_cli import build
from .mapping_cli import export_html


def register_parser(sub):
    cmd=sub.add_parser('correct-distal-preview',help='Compare bounded ankle/wrist corrections with original weights')
    for name in ('manifest','workspace','mesh','html'):cmd.add_argument('--'+name,type=Path,required=True)
    cmd.add_argument('--output',type=Path)


def analyze(mesh,skeleton):
    if mesh.get('profile') not in ('partition-full-alpha-supported-v2','partition-distal-axis-support-v1') or mesh['source_skeleton_sha256']!=canonical_sha256(skeleton):
        raise ValueError('distal_corrective_source_mismatch')
    bones={b['id']:b for b in skeleton['bones']};layers=[]
    for row in mesh['layers']:
        if len(row['bone_ids'])!=3 or not row['weights']:continue
        chain=[bones[b] for b in row['bone_ids']];context=prepare(row,chain)
        samples=[sample(context,angle) for angle in ANGLES]
        layers.append({'layer_id':row['layer_id'],'joint_id':chain[2]['id'],'triangles':row['triangles'],
                       'projection_budget_px':context['budget'],'free_vertex_count':sum(context['free']),
                       'status':'candidate_requires_review' if all(s['qa']['passed'] for s in samples) else 'blocked',
                       'samples':samples})
    return {'schema':'autospine.distal-corrective/v1','profile':'distal-half-angle-projection-48-v1','authority':'none',
            'production_authorized':False,'source_mesh_sha256':canonical_sha256(mesh),'source_skeleton_sha256':canonical_sha256(skeleton),
            'selected_method':None,'parameters':{'iterations':48,'area_targets':[.55,1.9],'edge_target':1.9,'angles':list(ANGLES),
                 'budget_fraction':.1,'budget_reference':'shorter_distal_segment','fixed_vertices':'zero_or_unit_distal_weight'},
            'layers':layers,'combined_motion_status':'not_evaluated','runtime_status':'not_evaluated','seam_status':'not_evaluated'}


def compile_report(state,manifest,digest,workspace):
    saved=read_mesh_report(state,manifest['dataset_id'],digest)
    if saved.get('profile')!='partition-full-alpha-supported-v2':raise ValueError('distal_corrective_profile_invalid')
    expected,(candidate,composite,_)=build(state,manifest,saved['source_mesh_sha256'],workspace,supported=True)
    if canonical_sha256(expected)!=digest:raise ValueError('distal_corrective_mesh_mismatch')
    skeleton=read_report(state,manifest['dataset_id'],'assisted-skeleton-candidates',saved['source_skeleton_sha256'])
    return analyze(saved,skeleton),(candidate,composite)


def read_corrective(state,manifest,digest,*,workspace):
    doc=read_mesh_report(state,manifest['dataset_id'],digest)
    expected,_=compile_report(state,manifest,doc['source_mesh_sha256'],workspace)
    if canonical_sha256(expected)!=canonical_sha256(doc):raise ValueError('distal_corrective_mismatch')
    return doc


def execute(args):
    from .distal_corrective_view import render_corrective
    manifest=read_input(args.manifest)
    doc,(candidate,composite)=compile_report(args.state_root,manifest,canonical_sha256(read_input(args.mesh)),args.workspace)
    export_html(args.html,render_corrective(candidate,composite,doc))
    return doc,'weighted-mesh-candidates',manifest['dataset_id'],0
