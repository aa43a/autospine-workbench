"""Exact ownership-page sources to a 4.3.26 diagnostic bundle and Editor images."""
import argparse
import hashlib
import json
from pathlib import Path
from ..resolved_project import canonical_sha256
from ..targets.spine43.ownership_preview import build_preview
from .artifacts import read_input,read_report
from .ownership_atlas_cli import compile_report as source_report
from .mesh_storage import read_mesh_report,publish_mesh_report,export_mesh
from .elbow_target_cli import archive,export


def compile_report(state,manifest,digest,workspace):
    atlas=read_mesh_report(state,manifest['dataset_id'],digest)
    if atlas.get('schema')!='autospine.ownership-atlas/v1':raise ValueError('ownership_target_source_invalid')
    expected,_,pages=source_report(state,manifest,atlas['source_partitions_sha256'],workspace)
    if canonical_sha256(expected)!=digest:raise ValueError('ownership_target_source_mismatch')
    skeleton=read_report(state,manifest['dataset_id'],'assisted-skeleton-candidates',atlas['source_skeleton_sha256'])
    scope,files=build_preview(atlas,skeleton,pages)
    files['preview-manifest.json']=json.dumps(scope,sort_keys=True,separators=(',',':')).encode()
    data=archive(files)
    if len(data)>32<<20:raise ValueError('ownership_target_archive_too_large')
    scope['zip_sha256']=hashlib.sha256(data).hexdigest()
    return scope,data,files


def read_preview(state,manifest,digest,*,workspace):
    saved=read_mesh_report(state,manifest['dataset_id'],digest)
    expected,_,_=compile_report(state,manifest,saved['source_atlas_sha256'],workspace)
    if canonical_sha256(saved)!=canonical_sha256(expected):raise ValueError('ownership_target_replay_mismatch')
    return saved


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-root',type=Path,default=Path(__file__).resolve().parents[3]/'workspace')
    for name in ('manifest','workspace','atlas','directory','output','zip'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        manifest=read_input(args.manifest)
        scope,data,files=compile_report(args.state_root,manifest,canonical_sha256(read_input(args.atlas)),args.workspace)
        digest=publish_mesh_report(args.state_root,manifest['dataset_id'],scope)
        export_mesh(args.output,scope);export(args.zip,data)
        for name,raw in files.items():export(args.directory/name,raw)
        print(json.dumps({'status':'written','artifact_sha256':digest,'regions':len(scope['regions']),'authority':'none'}));return 0
    except (ValueError,KeyError,TypeError,OSError,RuntimeError):
        print(json.dumps({'status':'blocked','reason_code':'ownership_target_request_failed','authority':'none'}));return 1


if __name__=='__main__':raise SystemExit(main())
