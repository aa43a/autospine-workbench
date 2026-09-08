"""Exact combined-pose evidence to linear continuous diagnostic bundle."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from ..resolved_project import canonical_sha256
from ..targets.spine43.continuous_bake import bake
from .combined_corrective_cli import compile_report as combined_source
from .artifacts import read_input
from .mesh_storage import read_mesh_report,publish_mesh_report,export_mesh
from .elbow_target_cli import archive,export


def compile_report(state,manifest,source_sha,workspace):
    saved=read_mesh_report(state,manifest['dataset_id'],source_sha)
    if saved['schema']!='autospine.combined-corrective-preview/v1':raise ValueError('continuous_source_schema_invalid')
    scope,_,files=combined_source(state,manifest,saved['source_original_atlas_sha256'],saved['source_width_sha256'],workspace)
    if canonical_sha256(scope)!=source_sha:raise ValueError('continuous_source_replay_mismatch')
    doc,qa=bake(json.loads(files['skeleton.json']))
    encode=lambda value:json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    files.pop('preview-manifest.json');scope.pop('zip_sha256')
    files['skeleton.json']=encode(doc);editor=deepcopy(doc);editor['skeleton']['images']='./images/'
    files['editor/skeleton.json']=encode(editor)
    scope.update(schema='autospine.continuous-corrective-preview/v1',profile='bilinear-field-linear-bake-v1',
        source_combined_sha256=source_sha,animation='continuous_corrective_inspection',
        continuous_motion_status='sampled_only',bake_fps=30,bake_qa=qa)
    scope['files']={k:hashlib.sha256(v).hexdigest() for k,v in files.items()}
    files['preview-manifest.json']=encode(scope);data=archive(files)
    if len(data)>32<<20:raise ValueError('continuous_archive_too_large')
    scope['zip_sha256']=hashlib.sha256(data).hexdigest()
    return scope,data,files


def read_continuous(state,manifest,digest,*,workspace):
    saved=read_mesh_report(state,manifest['dataset_id'],digest)
    expected,_,_=compile_report(state,manifest,saved['source_combined_sha256'],workspace)
    if canonical_sha256(expected)!=canonical_sha256(saved):raise ValueError('continuous_replay_mismatch')
    return saved


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-root',type=Path,default=Path(__file__).resolve().parents[3]/'workspace')
    for name in ('manifest','workspace','source','directory','output','zip'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        scope,data,files=compile_report(args.state_root,read_input(args.manifest),canonical_sha256(read_input(args.source)),args.workspace)
        digest=publish_mesh_report(args.state_root,scope.get('dataset_id',read_input(args.manifest)['dataset_id']),scope)
        export_mesh(args.output,scope);export(args.zip,data)
        for name,raw in files.items():export(args.directory/name,raw)
        print(json.dumps({'status':'written','artifact_sha256':digest,'qa':scope['bake_qa']}));return 0
    except (ValueError,TypeError,KeyError,OSError,RuntimeError):
        print(json.dumps({'status':'blocked','reason_code':'continuous_preview_failed','authority':'none'}));return 1


if __name__=='__main__':raise SystemExit(main())
