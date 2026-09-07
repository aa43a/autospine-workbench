"""Source-bound experimental three-bone alpha-grid mesh generation."""
from pathlib import Path
from ..resolved_project import canonical_sha256
from .artifacts import read_input, read_report, publish_report
from .mapping_cli import export_html
from .layer_binding_cli import read_layer_binding_draft,read_layer_bindings
from .region_binding_cli import sources
from .mesh_storage import read_mesh_report,publish_mesh_report


def register_parser(sub):
    cmd=sub.add_parser('build-weighted-mesh',help='Generate and probe experimental three-bone weighted meshes')
    for name in ('manifest','workspace','draft','html'):
        cmd.add_argument('--'+name,required=True,type=Path)
    cmd.add_argument('--output',type=Path)


def inputs(state,manifest,digest,workspace):
    draft=read_layer_binding_draft(state,manifest,digest,workspace=workspace)
    bindings=read_layer_bindings(state,manifest,draft['source_bindings_sha256'],workspace=workspace)
    candidate,assisted,skeleton,composite,images=sources(state,manifest,bindings['source_skeleton_sha256'],workspace)
    return candidate,assisted,skeleton,bindings,draft,composite,images


def read_mesh_candidate(state,manifest,digest,*,workspace):
    from ..asset.joints.mesh_candidate import validate_mesh_candidate
    doc=read_mesh_report(state,manifest['dataset_id'],digest)
    candidate,assisted,skeleton,bindings,draft,_,images=inputs(state,manifest,doc['source_draft_sha256'],workspace)
    return validate_mesh_candidate(candidate,assisted,skeleton,bindings,draft,images,doc)


def execute(args):
    from ..asset.joints.mesh_candidate import build_mesh_candidate
    from .mesh_candidate_view import render_mesh_candidate
    manifest=read_input(args.manifest)
    candidate,assisted,skeleton,bindings,draft,composite,images=inputs(
        args.state_root,manifest,canonical_sha256(read_input(args.draft)),args.workspace)
    doc=build_mesh_candidate(candidate,assisted,skeleton,bindings,draft,images)
    html=render_mesh_candidate(candidate,doc,composite,images)
    digest=publish_mesh_report(args.state_root,manifest['dataset_id'],doc)
    read_mesh_candidate(args.state_root,manifest,digest,workspace=args.workspace)
    export_html(args.html,html)
    return doc,'weighted-mesh-candidates',manifest['dataset_id'],0
