"""Compare elbow strategies through exact source readers and immutable reports."""
from pathlib import Path
from ..resolved_project import canonical_sha256
from ..asset.joints.elbow_comparison import build_comparison,validate_comparison
from .artifacts import read_input,read_report
from .mesh_area_cli import sources
from .mapping_cli import export_html


def register_parser(sub):
    cmd = sub.add_parser('compare-elbow-deformation',help='Compare LBS, auxiliary bone and corrective deformation')
    for name in ('manifest','workspace','mesh','html'):
        cmd.add_argument('--'+name,type=Path,required=True)
    cmd.add_argument('--output',type=Path)


def read_comparison(state,manifest,digest,*,workspace):
    doc = read_report(state,manifest['dataset_id'],'elbow-comparisons',digest)
    mesh,skeleton = sources(state,manifest,doc['source_mesh_sha256'],workspace)
    return validate_comparison(mesh,skeleton,doc)


def execute(args):
    from .elbow_comparison_view import render_comparison
    manifest = read_input(args.manifest)
    mesh,skeleton = sources(args.state_root,manifest,canonical_sha256(read_input(args.mesh)),args.workspace)
    doc = build_comparison(mesh,skeleton)
    export_html(args.html,render_comparison(mesh,skeleton,doc))
    return doc,'elbow-comparisons',manifest['dataset_id'],0
