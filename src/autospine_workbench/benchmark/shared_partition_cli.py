"""Package shared-texture partition v2 with exact v1/mesh provenance."""
import argparse
import hashlib
from io import BytesIO
import json
from pathlib import Path
from zipfile import ZipFile

from ..asset.joints.shared_partitions import combine_layer
from ..resolved_project import canonical_sha256
from .artifacts import read_input,read_report
from .partition_coverage_cli import build as build_mesh
from .partition_cli import build as build_partitions
from .mesh_storage import read_mesh_report,publish_mesh_report,export_mesh
from .elbow_target_cli import archive,export
from .mapping_cli import export_html


def compile_report(state,manifest,digest,workspace):
    mesh=read_mesh_report(state,manifest['dataset_id'],digest)
    if mesh.get('profile')!='partition-full-alpha-supported-v2':raise ValueError('shared_partition_profile_invalid')
    expected,(_,_,images)=build_mesh(state,manifest,mesh['source_mesh_sha256'],workspace,supported=True)
    if canonical_sha256(expected)!=digest:raise ValueError('shared_partition_mesh_mismatch')
    old=read_report(state,manifest['dataset_id'],'layer-partitions',mesh['source_partitions_sha256'])
    partitions,data,_=build_partitions(state,manifest,old['source_structure_sha256'],workspace)
    if canonical_sha256(partitions)!=mesh['source_partitions_sha256']:raise ValueError('shared_partition_source_mismatch')
    files={};layers=[]
    with ZipFile(BytesIO(data)) as zipped:
        for metadata in partitions['layers']:
            name=metadata['layer_id']
            source=zipped.read(name+'/source.png');ownership=zipped.read(name+'/ownership.png')
            rows=[r for r in mesh['layers'] if r['source_layer_id']==name]
            layers.append(combine_layer(source,ownership,metadata,rows,images))
            files[name+'/source.png']=source;files[name+'/ownership.png']=ownership
    doc={'schema':'autospine.layer-partitions/v2','profile':'shared-source-regional-weights-v1','authority':'none',
        'production_authorized':False,'source_partitions_sha256':canonical_sha256(partitions),'source_mesh_sha256':digest,
        'source_skeleton_sha256':mesh['source_skeleton_sha256'],'residual_policy':'retain_original',
        'texture_sampling':'ownership_mask_required','layers':layers,
        'files':{n:hashlib.sha256(b).hexdigest() for n,b in files.items()},
        'runtime_status':'not_evaluated','seam_status':'not_evaluated'}
    files['partition-v2.json']=json.dumps(doc,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    bundle=archive(files)
    if len(bundle)>32<<20:raise ValueError('shared_partition_archive_too_large')
    doc['zip_sha256']=hashlib.sha256(bundle).hexdigest()
    return doc,bundle,files


def read_shared(state,manifest,digest,*,workspace):
    saved=read_mesh_report(state,manifest['dataset_id'],digest)
    expected,_,_=compile_report(state,manifest,saved['source_mesh_sha256'],workspace)
    if canonical_sha256(expected)!=canonical_sha256(saved):raise ValueError('shared_partition_replay_mismatch')
    return saved


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-root',type=Path,default=Path(__file__).resolve().parents[3]/'workspace')
    for name in ('manifest','workspace','mesh','html','output','zip'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        from .shared_partition_view import render
        manifest=read_input(args.manifest)
        doc,bundle,files=compile_report(args.state_root,manifest,canonical_sha256(read_input(args.mesh)),args.workspace)
        digest=publish_mesh_report(args.state_root,manifest['dataset_id'],doc)
        export_mesh(args.output,doc);export(args.zip,bundle);export_html(args.html,render(doc,files))
        print(json.dumps({'status':'written','artifact_sha256':digest,'source_layers':len(doc['layers']),
            'regions':sum(len(r['partitions']) for r in doc['layers']),'authority':'none'}))
        return 0
    except (OSError,RuntimeError,ValueError,TypeError,KeyError):
        print(json.dumps({'status':'blocked','reason_code':'shared_partition_request_failed','authority':'none'}));return 1


if __name__=='__main__':raise SystemExit(main())
