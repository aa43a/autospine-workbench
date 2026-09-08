"""Build multi-region weight experiments from exact unmodified partition sources."""
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile
from ..resolved_project import canonical_sha256
from ..asset.joints.partition_mesh import build_region
from .artifacts import read_input,read_report
from .partition_cli import build
from .mesh_candidate_cli import inputs
from .mesh_storage import read_mesh_report
from .mapping_cli import export_html


def register_parser(sub):
    cmd=sub.add_parser('build-partition-mesh',help='Build experimental per-side mesh weights with retained residuals')
    for name in ('manifest','workspace','partitions','html'):
        cmd.add_argument('--'+name,type=Path,required=True)
    cmd.add_argument('--output',type=Path)


def compile_report(state,manifest,digest,workspace):
    saved=read_report(state,manifest['dataset_id'],'layer-partitions',digest)
    partitions,data,(candidate,composite,_)=build(state,manifest,saved['source_structure_sha256'],workspace)
    if canonical_sha256(partitions)!=digest:raise ValueError('partition_mesh_source_mismatch')
    structure=read_report(state,manifest['dataset_id'],'structure-candidates',saved['source_structure_sha256'])
    _,_,skeleton,_,_,_,_=inputs(state,manifest,structure['source_draft_sha256'],workspace)
    source_layers={r['layer_id']:r for r in candidate['layers']};regions=[];images={};view_layers=[];residual=[]
    with ZipFile(BytesIO(data)) as zipped:
        for part in partitions['layers']:
            layer_id=part['layer_id'];source=source_layers[layer_id]
            proposal=next(r for r in structure['layers'] if r['layer_id']==layer_id)
            for side,name in (('l','left'),('r','right')):
                bones=next(c['bone_ids'] for c in proposal['components'] if c['side']==side)
                raw=zipped.read(layer_id+'/'+name+'.png');row=build_region(raw,source,side,bones,skeleton)
                regions.append(row);images[row['layer_id']]=raw
                view_layers.append({**source,'layer_id':row['layer_id'],'image_sha256':row['image_sha256'],'name':source['name']+' / '+side})
            residual.append({'layer_id':layer_id,'file':layer_id+'/residual.png',
                             'sha256':partitions['files'][layer_id+'/residual.png'],'status':'preserved_unbound'})
    doc={'schema':'autospine.partition-mesh/v1','profile':'partition-joint-plane-grid-v1','authority':'none',
         'production_authorized':False,'source_partitions_sha256':digest,'source_skeleton_sha256':canonical_sha256(skeleton),
         'residual_policy':'retain_original','residuals':residual,'layers':regions,
         'seam_status':'not_evaluated','runtime_status':'not_evaluated'}
    return doc,({**candidate,'layers':view_layers},composite,images)


def read_partition_mesh(state,manifest,digest,*,workspace):
    doc=read_mesh_report(state,manifest['dataset_id'],digest)
    if doc.get('profile') in ('partition-full-alpha-v2','partition-full-alpha-supported-v2'):
        from .partition_coverage_cli import read_coverage
        return read_coverage(state,manifest,digest,workspace=workspace)
    expected,_=compile_report(state,manifest,doc['source_partitions_sha256'],workspace)
    if canonical_sha256(doc)!=canonical_sha256(expected):raise ValueError('partition_mesh_mismatch')
    return doc


def execute(args):
    from .partition_mesh_view import render_mesh
    manifest=read_input(args.manifest)
    doc,(candidate,composite,images)=compile_report(args.state_root,manifest,canonical_sha256(read_input(args.partitions)),args.workspace)
    export_html(args.html,render_mesh(candidate,doc,composite,images))
    return doc,'weighted-mesh-candidates',manifest['dataset_id'],0
