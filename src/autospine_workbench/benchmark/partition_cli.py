"""Replay structure candidates and export lossless diagnostic partitions."""
import hashlib
import json
from pathlib import Path

from ..resolved_project import canonical_sha256
from ..asset.joints.partition_pixels import partition
from .artifacts import read_input, read_report, publish_report
from .mesh_candidate_cli import inputs
from .structure_cli import read_structure
from .elbow_target_cli import archive, export
from .mapping_cli import export_html


def register_parser(sub):
    cmd=sub.add_parser('partition-layer-candidates',help='Export lossless component partition previews')
    for name in ('manifest','workspace','structure','zip','html'):
        cmd.add_argument('--'+name,type=Path,required=True)
    cmd.add_argument('--output',type=Path)


def build(state,manifest,digest,workspace):
    structure=read_structure(state,manifest,digest,workspace=workspace)
    candidate,_,_,_,_,composite,images=inputs(state,manifest,structure['source_draft_sha256'],workspace)
    sources={r['layer_id']:r for r in candidate['layers']};files={};rows=[];views=[]
    for row in structure['layers']:
        if not row['proposal'] or row['proposal']['kind']!='component_partition':continue
        source=sources[row['layer_id']]
        parts,qa=partition(images[row['layer_id']],source,row)
        files[row['layer_id']+'/source.png']=images[row['layer_id']]
        for name,data in parts.items():files[row['layer_id']+'/'+name]=data
        rows.append({'layer_id':row['layer_id'],'bbox':source['bbox'],
                     'source_image_sha256':source['image_sha256'],'qa':qa,
                     'status':'needs_review','reason_code':'partition_assignment_review_required'})
        views.append((source,parts,qa))
    report={'schema':'autospine.layer-partitions/v1','profile':'component-ownership-lossless-v1',
            'authority':'none','production_authorized':False,'source_structure_sha256':digest,
            'parameters':{'alpha_threshold':8,'satellite_margin_px':1,'low_alpha_distance':'four_connected',
                          'ties':'residual','transparent_rgb':'residual','ownership_codes':{'left':1,'right':2,'residual':3}},
            'layers':rows,'files':{k:hashlib.sha256(v).hexdigest() for k,v in files.items()}}
    files['partition-manifest.json']=json.dumps(report,sort_keys=True,indent=2).encode()
    data=archive(files)
    if len(data)>32<<20:raise ValueError('partition_archive_too_large')
    report['zip_sha256']=hashlib.sha256(data).hexdigest()
    return report,data,(candidate,composite,views)


def read_partitions(state,manifest,digest,*,workspace):
    doc=read_report(state,manifest['dataset_id'],'layer-partitions',digest)
    expected,_,_=build(state,manifest,doc['source_structure_sha256'],workspace)
    if canonical_sha256(doc)!=canonical_sha256(expected):raise ValueError('partition_report_mismatch')
    return doc


def execute(args):
    from .partition_view import render_partitions
    manifest=read_input(args.manifest)
    doc,data,view=build(args.state_root,manifest,canonical_sha256(read_input(args.structure)),args.workspace)
    publish_report(args.state_root,manifest['dataset_id'],'layer-partitions',doc)
    export(args.zip,data);export_html(args.html,render_partitions(*view))
    return doc,'layer-partitions',manifest['dataset_id'],0
