"""Source-bound local correction diagnostics, stored separately from prior meshes."""
from pathlib import Path
from ..resolved_project import canonical_sha256
from ..asset.joints.elbow_constraint_report import build_report,validate_report
from .artifacts import read_input,read_report
from .mesh_area_cli import sources
from .mapping_cli import export_html


def register_parser(sub):
    cmd = sub.add_parser('correct-elbow-preview',help='Apply bounded area and edge constraints to elbow preview')
    for name in ('manifest','workspace','mesh','html'):cmd.add_argument('--'+name,type=Path,required=True)
    cmd.add_argument('--output',type=Path)


def read_constraints(state,manifest,digest,*,workspace):
    doc = read_report(state,manifest['dataset_id'],'elbow-constraints',digest)
    mesh,skeleton = sources(state,manifest,doc['source_mesh_sha256'],workspace)
    return validate_report(mesh,skeleton,doc)


def execute(args):
    from .elbow_constraint_view import render
    manifest = read_input(args.manifest)
    mesh,skeleton = sources(args.state_root,manifest,canonical_sha256(read_input(args.mesh)),args.workspace)
    doc = build_report(mesh,skeleton)
    export_html(args.html,render(mesh,skeleton,doc))
    return doc,'elbow-constraints',manifest['dataset_id'],0
