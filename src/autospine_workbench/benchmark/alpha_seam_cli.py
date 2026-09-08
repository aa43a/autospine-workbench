"""Exact continuous source to alpha contour/local seam diagnostic bundle."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from ..resolved_project import canonical_sha256
from ..targets.spine43.alpha_seam_bake import bake
from .continuous_corrective_cli import compile_report as continuous_source
from .artifacts import read_input
from .mesh_storage import read_mesh_report,publish_mesh_report,export_mesh
from .elbow_target_cli import archive,export


def compile_report(state,manifest,digest,workspace):
    saved=read_mesh_report(state,manifest['dataset_id'],digest)
    if saved['schema']!='autospine.continuous-corrective-preview/v1':raise ValueError('alpha_seam_source_invalid')
    scope,_,files=continuous_source(state,manifest,saved['source_combined_sha256'],workspace)
    if canonical_sha256(scope)!=digest:raise ValueError('alpha_seam_source_replay_mismatch')
    doc,qa=bake(json.loads(files['skeleton.json']),files)
    encode=lambda v:json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    scope.pop('zip_sha256');files.pop('preview-manifest.json')
    files['skeleton.json']=encode(doc);editor=deepcopy(doc);editor['skeleton']['images']='./images/'
    files['editor/skeleton.json']=encode(editor)
    scope.update(schema='autospine.alpha-seam-preview/v1',profile='alpha-barycentric-smoothed-projection-v1',
        source_continuous_sha256=digest,animation='alpha_seam_inspection',alpha_seam_qa=qa,bake_qa=qa['geometry'])
    scope['files']={k:hashlib.sha256(v).hexdigest() for k,v in files.items()}
    files['preview-manifest.json']=encode(scope);data=archive(files)
    if len(data)>32<<20:raise ValueError('alpha_seam_archive_too_large')
    scope['zip_sha256']=hashlib.sha256(data).hexdigest()
    return scope,data,files


def read_alpha_seam(state,manifest,digest,*,workspace):
    saved=read_mesh_report(state,manifest['dataset_id'],digest)
    expected,_,_=compile_report(state,manifest,saved['source_continuous_sha256'],workspace)
    if canonical_sha256(expected)!=canonical_sha256(saved):raise ValueError('alpha_seam_replay_mismatch')
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
        print(json.dumps({'status':'written','artifact_sha256':digest,'qa_status':scope['alpha_seam_qa']['status']}));return 0
    except (ValueError,TypeError,KeyError,OSError,RuntimeError):
        print(json.dumps({'status':'blocked','reason_code':'alpha_seam_preview_failed','authority':'none'}));return 1


if __name__=='__main__':raise SystemExit(main())
