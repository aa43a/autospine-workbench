"""Exact continuous-anchor bundle to tangent/area-guarded shape experiment."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from ..resolved_project import canonical_sha256
from ..targets.spine43.seam_shape_bake import bake
from ..targets.spine43.same_frame_seam import analyze as raster
from .continuous_anchor_cli import compile_report as anchor_source
from .artifacts import read_input
from .mesh_storage import read_mesh_report,publish_mesh_report,export_mesh
from .elbow_target_cli import archive,export
from .seam_shape_view import render


def compile_report(state,manifest,digest,workspace):
    saved=read_mesh_report(state,manifest['dataset_id'],digest)
    if saved['schema']!='autospine.continuous-anchor-preview/v1':raise ValueError('shape_source_schema')
    previous,_,files=anchor_source(state,manifest,saved['source_parameters_sha256'],workspace)
    if canonical_sha256(previous)!=digest:raise ValueError('shape_source_replay')
    parameters=read_mesh_report(state,manifest['dataset_id'],saved['source_parameters_sha256'])
    prior=json.loads(files['skeleton.json']);source=deepcopy(prior);animation=source['animations'].pop('continuous-anchor-inspection')
    for c in previous['alpha_seam_qa']['constraints']:animation['attachments']['default'].pop(c['follower'])
    source['animations']['continuous-corrective-inspection']=animation
    encode=lambda v:json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    continuous=read_mesh_report(state,manifest['dataset_id'],previous['source_continuous_sha256'])
    if hashlib.sha256(encode(source)).hexdigest()!=continuous['files']['skeleton.json']:raise ValueError('shape_continuous_hash')
    doc,qa=bake(source,files,previous['alpha_seam_qa']['before'],parameters)
    original=previous['alpha_seam_qa']['after'];comparison,images=raster(prior,doc,files,original['boundaries'],original['relations'])
    scope=deepcopy(previous);scope.pop('zip_sha256');scope.pop('alpha_seam_qa');files.pop('preview-manifest.json')
    files.update({'shape-raster/'+n:v for n,v in images.items()});files['skeleton.json']=encode(doc)
    editor=deepcopy(doc);editor['skeleton']['images']='./images/';files['editor/skeleton.json']=encode(editor)
    scope.update(schema='autospine.seam-shape-preview/v1',profile='local-tangent2-smooth008-ridge001-v1',
        source_anchor_sha256=digest,animation='seam_shape_inspection',shape_qa=qa,bake_qa=qa['geometry'],
        common_frame_comparison=comparison,status='blocked' if qa['status']=='blocked' else 'needs_review')
    scope['files']={n:hashlib.sha256(raw).hexdigest() for n,raw in files.items()};files['preview-manifest.json']=encode(scope)
    data=archive(files)
    if len(data)>32<<20:raise ValueError('shape_archive_too_large')
    scope['zip_sha256']=hashlib.sha256(data).hexdigest();return scope,data,files


def read_shape(state,manifest,digest,*,workspace):
    saved=read_mesh_report(state,manifest['dataset_id'],digest)
    if saved['schema']!='autospine.seam-shape-preview/v1':raise ValueError('shape_reader_schema')
    expected,_,_=compile_report(state,manifest,saved['source_anchor_sha256'],workspace)
    if canonical_sha256(expected)!=digest:raise ValueError('shape_reader_mismatch')
    return saved


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--state-root',type=Path,default=Path(__file__).resolve().parents[3]/'workspace')
    for name in ('manifest','workspace','source','directory','output','zip'):p.add_argument('--'+name,type=Path,required=True)
    args=p.parse_args(argv)
    try:
        manifest=read_input(args.manifest);scope,data,files=compile_report(args.state_root,manifest,canonical_sha256(read_input(args.source)),args.workspace)
        digest=publish_mesh_report(args.state_root,manifest['dataset_id'],scope);export_mesh(args.output,scope);export(args.zip,data)
        for name,raw in files.items():export(args.directory/name,raw)
        export(args.directory/'raster-review.html',render(scope).encode())
        print(json.dumps({'status':'written','artifact_sha256':digest}));return 0
    except (ValueError,TypeError,KeyError,OSError,RuntimeError):
        print(json.dumps({'status':'blocked','reason_code':'seam_shape_failed','authority':'none'}));return 1


if __name__=='__main__':raise SystemExit(main())
