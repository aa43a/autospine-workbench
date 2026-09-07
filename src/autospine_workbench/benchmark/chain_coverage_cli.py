"""Exact alpha diagnostics for mesh-chain candidates, independent of adoption."""
from pathlib import Path

from ..resolved_project import canonical_sha256
from .artifacts import read_input, read_report, publish_report
from .mapping_cli import export_html
from .region_binding_cli import sources
from .layer_binding_cli import read_layer_bindings, read_layer_binding_draft


def register_parser(sub):
    cmd = sub.add_parser('analyze-chain-coverage', help='Analyze alpha components and bone coverage before weighting')
    for name in ('manifest','workspace','bindings','html'):
        cmd.add_argument('--'+name,required=True,type=Path)
    for name in ('draft','output'):
        cmd.add_argument('--'+name,type=Path)


def inputs(state_root,manifest,digest,workspace):
    bindings=read_layer_bindings(state_root,manifest,digest,workspace=workspace)
    candidate,assisted,skeleton,composite,images=sources(state_root,manifest,bindings['source_skeleton_sha256'],workspace)
    return candidate,assisted,skeleton,bindings,composite,images


def read_chain_coverage(state_root,manifest,digest,*,workspace):
    from ..asset.joints.chain_coverage import validate_chain_coverage
    doc=read_report(state_root,manifest['dataset_id'],'chain-coverage',digest)
    candidate,assisted,skeleton,bindings,_,images=inputs(state_root,manifest,doc['source_bindings_sha256'],workspace)
    return validate_chain_coverage(candidate,assisted,skeleton,bindings,images,doc)


def execute(args):
    from ..asset.joints.chain_coverage import build_chain_coverage
    from .chain_coverage_view import render_chain_coverage
    from .layer_binding_draft import build_layer_binding_draft,validate_layer_binding_draft
    manifest=read_input(args.manifest)
    candidate,assisted,skeleton,bindings,composite,images=inputs(
        args.state_root,manifest,canonical_sha256(read_input(args.bindings)),args.workspace)
    draft=build_layer_binding_draft(bindings)
    if args.draft:
        draft=read_layer_binding_draft(args.state_root,manifest,canonical_sha256(read_input(args.draft)),workspace=args.workspace)
        validate_layer_binding_draft(bindings,draft)
    doc=build_chain_coverage(candidate,assisted,skeleton,bindings,images)
    html=render_chain_coverage(candidate,skeleton,bindings,doc,composite,images,draft)
    digest=publish_report(args.state_root,manifest['dataset_id'],'chain-coverage',doc)
    read_chain_coverage(args.state_root,manifest,digest,workspace=args.workspace)
    export_html(args.html,html)
    return doc,'chain-coverage',manifest['dataset_id'],0
