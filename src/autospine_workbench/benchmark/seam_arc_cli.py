"""Exact curve candidates to local supported arcs and ordered pair proposals."""
import argparse
import json
from pathlib import Path
from ..resolved_project import canonical_sha256
from ..targets.spine43.seam_arcs import analyze
from ..targets.spine43.seam_arc_validation import validate
from .alpha_curve_cli import compile_report as curve_source
from .artifacts import read_input
from .mesh_storage import read_mesh_report,publish_mesh_report,export_mesh
from .elbow_target_cli import export
from .seam_arc_view import render


def compile_report(state,manifest,digest,workspace):
    saved=read_mesh_report(state,manifest['dataset_id'],digest)
    if saved['schema']!='autospine.alpha-curve-anchors/v1':raise ValueError('arc_source_schema')
    curves,files=curve_source(state,manifest,saved['source_remap_sha256'],workspace)
    if canonical_sha256(curves)!=digest:raise ValueError('arc_source_replay')
    remap=read_mesh_report(state,manifest['dataset_id'],saved['source_remap_sha256'])
    result={'schema':'autospine.seam-arc-pairs/v1','source_curves_sha256':digest,
            'analysis':analyze(json.loads(files['skeleton.json']),curves,remap['alpha_seam_qa']['after']),
            'authority':'none','production_authorized':False,'status':'needs_review'}
    return validate(result),curves,files


def read_arcs(state,manifest,digest,*,workspace):
    saved=read_mesh_report(state,manifest['dataset_id'],digest)
    if saved['schema']!='autospine.seam-arc-pairs/v1':raise ValueError('arc_reader_schema')
    expected,_,_=compile_report(state,manifest,saved['source_curves_sha256'],workspace)
    if canonical_sha256(expected)!=digest:raise ValueError('arc_reader_mismatch')
    return saved


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-root',type=Path,default=Path(__file__).resolve().parents[3]/'workspace')
    for key in ('manifest','workspace','source','output','html'):parser.add_argument('--'+key,type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        manifest=read_input(args.manifest)
        report,curves,files=compile_report(args.state_root,manifest,canonical_sha256(read_input(args.source)),args.workspace)
        digest=publish_mesh_report(args.state_root,manifest['dataset_id'],report)
        export_mesh(args.output,report);export(args.html,render(report,curves,files).encode())
        print(json.dumps({'status':'written','artifact_sha256':digest}));return 0
    except (ValueError,KeyError,TypeError,OSError,RuntimeError):
        print(json.dumps({'status':'blocked','reason_code':'arc_build_failed','authority':'none'}));return 1


if __name__=='__main__':raise SystemExit(main())
