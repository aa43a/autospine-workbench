"""Replay the remap source and publish directed contour anchor candidates."""
import argparse
import hashlib
import json
from pathlib import Path
from ..resolved_project import canonical_sha256
from ..targets.spine43.alpha_curves import analyze
from ..targets.spine43.alpha_curve_validation import validate
from .artifacts import read_input
from .mesh_storage import read_mesh_report,publish_mesh_report,export_mesh
from .seam_remap_cli import compile_report as remap_source
from .elbow_target_cli import export
from .alpha_curve_view import render


def compile_report(state,manifest,digest,workspace):
    saved=read_mesh_report(state,manifest['dataset_id'],digest)
    if saved['schema']!='autospine.seam-remap-preview/v1':raise ValueError('curve_source_schema')
    scope,_,files=remap_source(state,manifest,saved['source_alpha_sha256'],workspace)
    if canonical_sha256(scope)!=digest:raise ValueError('curve_source_replay')
    return build(scope,files,digest),files


def build(scope,files,digest):
    for name,expected in scope['files'].items():
        if hashlib.sha256(files[name]).hexdigest()!=expected:raise ValueError('curve_file_hash')
    return validate({'schema':'autospine.alpha-curve-anchors/v1','source_remap_sha256':digest,
            'curves':analyze(json.loads(files['skeleton.json']),files,scope['alpha_seam_qa']['after']),
            'authority':'none','production_authorized':False,'status':'needs_review'})


def read_curves(state,manifest,digest,*,workspace):
    saved=read_mesh_report(state,manifest['dataset_id'],digest)
    if saved['schema']!='autospine.alpha-curve-anchors/v1':raise ValueError('curve_reader_schema')
    expected,_=compile_report(state,manifest,saved['source_remap_sha256'],workspace)
    if canonical_sha256(expected)!=digest:raise ValueError('curve_reader_mismatch')
    return saved


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-root',type=Path,default=Path(__file__).resolve().parents[3]/'workspace')
    for key in ('manifest','workspace','source','output','html'):parser.add_argument('--'+key,type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        manifest=read_input(args.manifest)
        report,files=compile_report(args.state_root,manifest,canonical_sha256(read_input(args.source)),args.workspace)
        digest=publish_mesh_report(args.state_root,manifest['dataset_id'],report)
        export_mesh(args.output,report);export(args.html,render(report,files).encode())
        print(json.dumps({'status':'written','artifact_sha256':digest}));return 0
    except (ValueError,KeyError,TypeError,OSError,RuntimeError):
        print(json.dumps({'status':'blocked','reason_code':'curve_build_failed','authority':'none'}));return 1


if __name__=='__main__':raise SystemExit(main())
