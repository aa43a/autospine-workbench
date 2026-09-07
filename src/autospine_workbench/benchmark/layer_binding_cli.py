"""Opt-in multi-bone binding candidates; v1 rigid readers remain unchanged."""
from pathlib import Path

from ..resolved_project import canonical_sha256
from .artifacts import read_input, read_report, publish_report, export_document
from .region_binding_cli import sources
from .mapping_cli import export_html


def register_parser(sub):
    cmd = sub.add_parser('build-layer-bindings', help='Review rigid and multi-bone limb binding candidates')
    for name in ('manifest', 'workspace', 'skeleton', 'html'):
        cmd.add_argument('--'+name, required=True, type=Path)
    for name in ('draft', 'draft-output', 'output'):
        cmd.add_argument('--'+name, type=Path)


def read_layer_bindings(state_root, manifest, digest, *, workspace):
    from ..asset.joints.layer_binding import validate_layer_bindings
    doc = read_report(state_root, manifest['dataset_id'], 'layer-binding-candidates-v2', digest)
    candidate, assisted, skeleton, _, _ = sources(state_root, manifest, doc['source_skeleton_sha256'], workspace)
    return validate_layer_bindings(candidate, assisted, skeleton, doc)


def read_layer_binding_draft(state_root, manifest, digest, *, workspace):
    from .layer_binding_draft import validate_layer_binding_draft
    draft = read_report(state_root, manifest['dataset_id'], 'layer-binding-drafts-v2', digest)
    doc = read_layer_bindings(state_root, manifest, draft['source_bindings_sha256'], workspace=workspace)
    return validate_layer_binding_draft(doc, draft)


def execute(args):
    from ..asset.joints.layer_binding import build_layer_bindings
    from .layer_binding_draft import build_layer_binding_draft, validate_layer_binding_draft
    from .layer_binding_view import render_layer_bindings
    manifest = read_input(args.manifest)
    candidate, assisted, skeleton, composite, images = sources(
        args.state_root, manifest, canonical_sha256(read_input(args.skeleton)), args.workspace)
    doc = build_layer_bindings(candidate, assisted, skeleton)
    draft = validate_layer_binding_draft(doc, read_input(args.draft)) if args.draft else build_layer_binding_draft(doc)
    html = render_layer_bindings(candidate, assisted, skeleton, doc, composite, images, draft)
    digest = publish_report(args.state_root, manifest['dataset_id'], 'layer-binding-candidates-v2', doc)
    read_layer_bindings(args.state_root, manifest, digest, workspace=args.workspace)
    draft_sha = publish_report(args.state_root, manifest['dataset_id'], 'layer-binding-drafts-v2', draft)
    read_layer_binding_draft(args.state_root, manifest, draft_sha, workspace=args.workspace)
    if args.draft_output:
        export_document(args.draft_output, draft)
    export_html(args.html, html)
    return doc, 'layer-binding-candidates-v2', manifest['dataset_id'], 2 if doc['status'] == 'blocked' else 0
