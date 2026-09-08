"""Replay local arcs and publish bounded continuous parameter candidates."""
import argparse
import json
from pathlib import Path
from ..resolved_project import canonical_sha256
from ..targets.spine43.continuous_seam_parameters import analyze
from ..targets.spine43.continuous_parameter_validation import validate
from .seam_arc_cli import compile_report as arc_source
from .artifacts import read_input
from .mesh_storage import read_mesh_report,publish_mesh_report,export_mesh
from .elbow_target_cli import export
from .continuous_parameter_view import render


def compile_report(state,manifest,digest,workspace):
    saved=read_mesh_report(state,manifest['dataset_id'],digest)
    if saved['schema']!='autospine.seam-arc-pairs/v1':raise ValueError('parameter_source_schema')
    arcs,curves,files=arc_source(state,manifest,saved['source_curves_sha256'],workspace)
    if canonical_sha256(arcs)!=digest:raise ValueError('parameter_source_replay')
    remap=read_mesh_report(state,manifest['dataset_id'],curves['source_remap_sha256'])
    return validate({'schema':'autospine.continuous-seam-parameters/v1','source_arcs_sha256':digest,
            'analysis':analyze(json.loads(files['skeleton.json']),curves,arcs,remap['alpha_seam_qa']['after']),
            'authority':'none','production_authorized':False,'status':'needs_review'})


def read_parameters(state,manifest,digest,*,workspace):
    saved=read_mesh_report(state,manifest['dataset_id'],digest)
    if saved['schema']!='autospine.continuous-seam-parameters/v1':raise ValueError('parameter_reader_schema')
    if canonical_sha256(compile_report(state,manifest,saved['source_arcs_sha256'],workspace))!=digest:
        raise ValueError('parameter_reader_mismatch')
    return saved


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--state-root',type=Path,default=Path(__file__).resolve().parents[3]/'workspace')
    for key in ('manifest','workspace','source','output','html'):p.add_argument('--'+key,type=Path,required=True)
    args=p.parse_args(argv)
    try:
        report=compile_report(args.state_root,read_input(args.manifest),canonical_sha256(read_input(args.source)),args.workspace)
        digest=publish_mesh_report(args.state_root,read_input(args.manifest)['dataset_id'],report)
        export_mesh(args.output,report);export(args.html,render(report).encode())
        print(json.dumps({'status':'written','artifact_sha256':digest}));return 0
    except (ValueError,KeyError,TypeError,OSError,RuntimeError):
        print(json.dumps({'status':'blocked','reason_code':'continuous_parameters_failed','authority':'none'}));return 1


if __name__=='__main__':raise SystemExit(main())
