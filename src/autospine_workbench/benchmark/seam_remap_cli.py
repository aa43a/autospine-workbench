"""Exact alpha candidate to a local conflict-remapped diagnostic bundle."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from ..resolved_project import canonical_sha256
from ..targets.spine43.seam_remap import bake
from ..targets.spine43.seam_raster import analyze as raster
from .alpha_seam_cli import compile_report as alpha_source
from .artifacts import read_input
from .mesh_storage import read_mesh_report,publish_mesh_report,export_mesh
from .elbow_target_cli import archive,export


def compile_report(state,manifest,digest,workspace):
    saved=read_mesh_report(state,manifest['dataset_id'],digest)
    if saved['schema']!='autospine.alpha-seam-preview/v1':raise ValueError('remap_source_schema_invalid')
    scope,_,files=alpha_source(state,manifest,saved['source_continuous_sha256'],workspace)
    if canonical_sha256(scope)!=digest:raise ValueError('remap_source_replay_mismatch')
    prior=json.loads(files['skeleton.json']);source=deepcopy(prior);animation=source['animations'].pop('alpha-seam-inspection')
    for c in scope['alpha_seam_qa']['constraints']:animation['attachments']['default'].pop(c['follower'])
    source['animations']['continuous-corrective-inspection']=animation
    encode=lambda v:json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    continuous=read_mesh_report(state,manifest['dataset_id'],scope['source_continuous_sha256'])
    if hashlib.sha256(encode(source)).hexdigest()!=continuous['files']['skeleton.json']:raise ValueError('remap_continuous_hash_mismatch')
    doc,qa=bake(source,files);before,before_images=raster(prior,files,scope['alpha_seam_qa']['after']);after,after_images=raster(doc,files,qa['after'])
    scope.pop('zip_sha256');files.pop('preview-manifest.json')
    files.update({'raster/before/'+n:v for n,v in before_images.items()});files.update({'raster/after/'+n:v for n,v in after_images.items()})
    files['skeleton.json']=encode(doc);editor=deepcopy(doc);editor['skeleton']['images']='./images/';files['editor/skeleton.json']=encode(editor)
    scope.update(schema='autospine.seam-remap-preview/v1',profile='alpha-local-conflict-remap-v1',source_alpha_sha256=digest,
        animation='remapped_seam_inspection',alpha_seam_qa=qa,bake_qa=qa['geometry'],raster_comparison={'before':before,'after':after})
    scope['files']={k:hashlib.sha256(v).hexdigest() for k,v in files.items()};files['preview-manifest.json']=encode(scope);data=archive(files)
    if len(data)>32<<20:raise ValueError('remap_archive_too_large')
    scope['zip_sha256']=hashlib.sha256(data).hexdigest();return scope,data,files


def read_remap(state,manifest,digest,*,workspace):
    saved=read_mesh_report(state,manifest['dataset_id'],digest)
    expected,_,_=compile_report(state,manifest,saved['source_alpha_sha256'],workspace)
    if canonical_sha256(expected)!=canonical_sha256(saved):raise ValueError('remap_replay_mismatch')
    return saved


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--state-root',type=Path,default=Path(__file__).resolve().parents[3]/'workspace')
    for name in ('manifest','workspace','source','directory','output','zip'):p.add_argument('--'+name,type=Path,required=True)
    args=p.parse_args(argv)
    try:
        manifest=read_input(args.manifest);scope,data,files=compile_report(args.state_root,manifest,canonical_sha256(read_input(args.source)),args.workspace)
        digest=publish_mesh_report(args.state_root,manifest['dataset_id'],scope);export_mesh(args.output,scope);export(args.zip,data)
        for name,raw in files.items():export(args.directory/name,raw)
        print(json.dumps({'status':'written','artifact_sha256':digest,'changes':len(scope['alpha_seam_qa']['remapping']['changes'])}));return 0
    except (ValueError,TypeError,KeyError,OSError,RuntimeError):
        print(json.dumps({'status':'blocked','reason_code':'seam_remap_failed','authority':'none'}));return 1


if __name__=='__main__':raise SystemExit(main())
