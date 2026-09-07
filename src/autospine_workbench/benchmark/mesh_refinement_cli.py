"""Refine an exact historical mesh without rewriting its grid or source selections."""
from pathlib import Path
from ..resolved_project import canonical_sha256
from .artifacts import read_input
from .mesh_storage import read_mesh_report,publish_mesh_report
from .mesh_candidate_cli import inputs,read_mesh_candidate
from .mapping_cli import export_html


def register_parser(sub):
    cmd=sub.add_parser('refine-mesh-weights',help='Refine exact three-bone mesh weights using joint planes')
    for name in ('manifest','workspace','mesh','html'):
        cmd.add_argument('--'+name,type=Path,required=True)
    cmd.add_argument('--output',type=Path)


def source(state,manifest,digest,workspace):
    # Only the baseline schema is allowed here, preventing recursive refinement chains.
    raw=read_mesh_report(state,manifest['dataset_id'],digest)
    if raw.get('schema')!='autospine.weighted-mesh-candidates/v1':
        raise ValueError('mesh_refinement_requires_baseline')
    baseline=read_mesh_candidate(state,manifest,digest,workspace=workspace)
    candidate,assisted,skeleton,bindings,draft,composite,images=inputs(state,manifest,baseline['source_draft_sha256'],workspace)
    return baseline,candidate,skeleton,bindings,draft,composite,images


def read_refinement(state,manifest,digest,*,workspace):
    from ..asset.joints.mesh_refinement import validate_mesh_refinement
    doc=read_mesh_report(state,manifest['dataset_id'],digest)
    baseline,_,skeleton,bindings,draft,_,_=source(state,manifest,doc['source_mesh_sha256'],workspace)
    return validate_mesh_refinement(baseline,skeleton,bindings,draft,doc)


def execute(args):
    from ..asset.joints.mesh_refinement import refine_mesh_weights
    from .mesh_refinement_view import render_refinement
    manifest=read_input(args.manifest)
    baseline,candidate,skeleton,bindings,draft,composite,images=source(
        args.state_root,manifest,canonical_sha256(read_input(args.mesh)),args.workspace)
    doc=refine_mesh_weights(baseline,skeleton,bindings,draft)
    html=render_refinement(candidate,baseline,doc,skeleton,composite,images)
    digest=publish_mesh_report(args.state_root,manifest['dataset_id'],doc)
    read_refinement(args.state_root,manifest,digest,workspace=args.workspace)
    export_html(args.html,html)
    return doc,'weighted-mesh-candidates',manifest['dataset_id'],0
