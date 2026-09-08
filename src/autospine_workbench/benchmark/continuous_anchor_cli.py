"""Continuous parameter candidate to a local baked Spine diagnostic bundle."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from ..resolved_project import canonical_sha256
from ..targets.spine43.continuous_seam_parameters import analyze as parameters
from ..targets.spine43.continuous_parameter_validation import validate
from ..targets.spine43.continuous_anchor_bake import bake
from ..targets.spine43.same_frame_seam import analyze as raster
from .seam_arc_cli import compile_report as arc_source
from .artifacts import read_input
from .mesh_storage import read_mesh_report,publish_mesh_report,export_mesh
from .elbow_target_cli import archive,export
from .continuous_anchor_view import render


def compile_report(state,manifest,digest,workspace):
    saved=read_mesh_report(state,manifest['dataset_id'],digest)
    if saved['schema']!='autospine.continuous-seam-parameters/v1':raise ValueError('anchor_source_schema')
    arc=read_mesh_report(state,manifest['dataset_id'],saved['source_arcs_sha256'])
    arcs,curves,files=arc_source(state,manifest,arc['source_curves_sha256'],workspace)
    if canonical_sha256(arcs)!=saved['source_arcs_sha256']:raise ValueError('anchor_arc_replay')
    remap=read_mesh_report(state,manifest['dataset_id'],curves['source_remap_sha256'])
    prior=json.loads(files['skeleton.json']);baseline=remap['alpha_seam_qa']['after']
    expected=validate({'schema':saved['schema'],'source_arcs_sha256':saved['source_arcs_sha256'],
        'analysis':parameters(prior,curves,arcs,baseline),'authority':'none','production_authorized':False,'status':'needs_review'})
    if canonical_sha256(expected)!=digest:raise ValueError('anchor_parameter_replay')
    source=deepcopy(prior);animation=source['animations'].pop('remapped-seam-inspection')
    for c in remap['alpha_seam_qa']['constraints']:animation['attachments']['default'].pop(c['follower'])
    source['animations']['continuous-corrective-inspection']=animation
    encode=lambda v:json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    continuous=read_mesh_report(state,manifest['dataset_id'],remap['source_continuous_sha256'])
    if hashlib.sha256(encode(source)).hexdigest()!=continuous['files']['skeleton.json']:raise ValueError('anchor_continuous_hash')
    doc,qa=bake(source,files,baseline,saved)
    comparison,images=raster(prior,doc,files,baseline['boundaries'],baseline['relations'])
    scope=deepcopy(remap);scope.pop('zip_sha256');files.pop('preview-manifest.json')
    files.update({'continuous-raster/'+n:v for n,v in images.items()})
    files['skeleton.json']=encode(doc);editor=deepcopy(doc);editor['skeleton']['images']='./images/';files['editor/skeleton.json']=encode(editor)
    scope.pop('raster_comparison',None)
    scope.update(schema='autospine.continuous-anchor-preview/v1',profile='continuous-anchor-frozen-local-solver-v1',
        source_parameters_sha256=digest,source_remap_sha256=curves['source_remap_sha256'],
        animation='continuous_anchor_inspection',alpha_seam_qa=qa,bake_qa=qa['geometry'],
        common_frame_comparison=comparison,status='blocked' if qa['status']=='blocked' else 'needs_review')
    scope['files']={n:hashlib.sha256(raw).hexdigest() for n,raw in files.items()};files['preview-manifest.json']=encode(scope)
    data=archive(files)
    if len(data)>32<<20:raise ValueError('anchor_archive_too_large')
    scope['zip_sha256']=hashlib.sha256(data).hexdigest();return scope,data,files


def read_anchor(state,manifest,digest,*,workspace):
    saved=read_mesh_report(state,manifest['dataset_id'],digest)
    if saved['schema']!='autospine.continuous-anchor-preview/v1':raise ValueError('anchor_reader_schema')
    expected,_,_=compile_report(state,manifest,saved['source_parameters_sha256'],workspace)
    if canonical_sha256(expected)!=digest:raise ValueError('anchor_reader_mismatch')
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
        print(json.dumps({'status':'blocked','reason_code':'continuous_anchor_failed','authority':'none'}));return 1


if __name__=='__main__':raise SystemExit(main())
