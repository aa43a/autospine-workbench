"""Bake corrective keys from exact historical meshes and preview original textures."""
from pathlib import Path
from ..resolved_project import canonical_sha256
from ..asset.joints.elbow_bake import build_bake,validate_bake
from .artifacts import read_input
from .mesh_storage import read_mesh_report
from .mesh_candidate_cli import read_mesh_candidate,inputs
from .mapping_cli import export_html


def register_parser(sub):
    cmd=sub.add_parser('bake-elbow-preview',help='Bake and preview a corrective elbow loop')
    for name in ('manifest','workspace','mesh','html'):cmd.add_argument('--'+name,type=Path,required=True)
    cmd.add_argument('--output',type=Path)


def sources(state,manifest,digest,workspace):
    mesh=read_mesh_candidate(state,manifest,digest,workspace=workspace)
    candidate,_,skeleton,_,_,_,images=inputs(state,manifest,mesh['source_draft_sha256'],workspace)
    return mesh,skeleton,candidate,images


def read_bake(state,manifest,digest,*,workspace):
    doc=read_mesh_report(state,manifest['dataset_id'],digest)
    mesh,skeleton,_,_=sources(state,manifest,doc['source_mesh_sha256'],workspace)
    return validate_bake(mesh,skeleton,doc)


def execute(args):
    from .elbow_bake_view import render
    manifest=read_input(args.manifest)
    mesh,skeleton,candidate,images=sources(args.state_root,manifest,canonical_sha256(read_input(args.mesh)),args.workspace)
    doc=build_bake(mesh,skeleton)
    export_html(args.html,render(mesh,skeleton,doc,candidate,images))
    return doc,'weighted-mesh-candidates',manifest['dataset_id'],0
