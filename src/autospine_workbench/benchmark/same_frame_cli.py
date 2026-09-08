"""Exact remap candidate to common-frame raster and segment-readiness report."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from ..resolved_project import canonical_sha256
from ..targets.spine43.alpha_seam_bake import bake as alpha_bake
from ..targets.spine43.same_frame_seam import analyze as compare
from ..targets.spine43.seam_segments import analyze as segments
from .seam_remap_cli import compile_report as remap_source
from .artifacts import read_input
from .mesh_storage import read_mesh_report,publish_mesh_report,export_mesh
from .elbow_target_cli import export
from .same_frame_view import render


def compile_report(state,manifest,digest,workspace):
    saved=read_mesh_report(state,manifest['dataset_id'],digest)
    if saved['schema']!='autospine.seam-remap-preview/v1':raise ValueError('same_frame_source_invalid')
    scope,_,files=remap_source(state,manifest,saved['source_alpha_sha256'],workspace)
    if canonical_sha256(scope)!=digest:raise ValueError('same_frame_replay_mismatch')
    after=json.loads(files['skeleton.json']);source=deepcopy(after);animation=source['animations'].pop('remapped-seam-inspection')
    for c in scope['alpha_seam_qa']['constraints']:animation['attachments']['default'].pop(c['follower'])
    source['animations']['continuous-corrective-inspection']=animation
    sha=lambda doc:hashlib.sha256(json.dumps(doc,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
    continuous=read_mesh_report(state,manifest['dataset_id'],scope['source_continuous_sha256'])
    if sha(source)!=continuous['files']['skeleton.json']:raise ValueError('same_frame_continuous_hash_mismatch')
    before,_=alpha_bake(source,files);alpha=read_mesh_report(state,manifest['dataset_id'],scope['source_alpha_sha256'])
    if sha(before)!=alpha['files']['skeleton.json']:raise ValueError('same_frame_alpha_hash_mismatch')
    boundary=scope['alpha_seam_qa']['after'];raster,images=compare(before,after,files,boundary['boundaries'],boundary['relations'])
    report={'schema':'autospine.same-frame-seam/v1','profile':'common-corridor-segment-readiness-v1',
        'source_remap_sha256':digest,'source_alpha_sha256':scope['source_alpha_sha256'],'raster':raster,'segments':segments(after,boundary),
        'authority':'none','production_authorized':False,'status':'needs_review','files':{n:hashlib.sha256(v).hexdigest() for n,v in images.items()}}
    return report,images


def read_same_frame(state,manifest,digest,*,workspace):
    saved=read_mesh_report(state,manifest['dataset_id'],digest)
    expected,_=compile_report(state,manifest,saved['source_remap_sha256'],workspace)
    if canonical_sha256(expected)!=canonical_sha256(saved):raise ValueError('same_frame_reader_mismatch')
    return saved


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--state-root',type=Path,default=Path(__file__).resolve().parents[3]/'workspace')
    for name in ('manifest','workspace','source','directory','output'):p.add_argument('--'+name,type=Path,required=True)
    args=p.parse_args(argv)
    try:
        manifest=read_input(args.manifest);report,images=compile_report(args.state_root,manifest,canonical_sha256(read_input(args.source)),args.workspace)
        digest=publish_mesh_report(args.state_root,manifest['dataset_id'],report);export_mesh(args.output,report)
        for n,raw in images.items():export(args.directory/n,raw)
        export(args.directory/'index.html',render(report).encode('utf-8'))
        print(json.dumps({'status':'written','artifact_sha256':digest}));return 0
    except (ValueError,TypeError,KeyError,OSError,RuntimeError):
        print(json.dumps({'status':'blocked','reason_code':'same_frame_failed','authority':'none'}));return 1


if __name__=='__main__':raise SystemExit(main())
