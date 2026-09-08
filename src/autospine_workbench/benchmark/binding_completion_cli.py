"""Complete missing head-detail options and retain unchanged reviewed choices."""
from pathlib import Path

from ..resolved_project import canonical_sha256
from ..asset.joints.binding_completion import build_completion, inherit_unchanged
from .artifacts import read_input, publish_report, export_document
from .layer_binding_cli import read_layer_bindings, read_layer_binding_draft
from .layer_binding_draft import validate_layer_binding_draft
from .layer_binding_view import render_layer_bindings
from .mapping_cli import export_html
from .region_binding_cli import sources


def register_parser(sub):
    cmd = sub.add_parser('complete-layer-bindings', help='Complete head-detail binding review')
    cmd.add_argument('--focus-layer', action='append', help='Layer ID to display initially; repeat for a subset')
    for name in ('manifest', 'workspace', 'draft', 'html', 'draft-output'):
        cmd.add_argument('--'+name, type=Path, required=True)
    for name in ('reviewed-draft', 'output'):
        cmd.add_argument('--'+name, type=Path)


def execute(args):
    manifest = read_input(args.manifest)
    old = read_layer_binding_draft(args.state_root, manifest, canonical_sha256(read_input(args.draft)),
                                   workspace=args.workspace)
    base = read_layer_bindings(args.state_root, manifest, old['source_bindings_sha256'], workspace=args.workspace)
    candidate, assisted, skeleton, composite, images = sources(
        args.state_root, manifest, base['source_skeleton_sha256'], args.workspace)
    document = build_completion(candidate, assisted, skeleton)
    draft = inherit_unchanged(base, old, document)
    if args.reviewed_draft:
        draft = validate_layer_binding_draft(document, read_input(args.reviewed_draft))
    html = render_layer_bindings(candidate, assisted, skeleton, document, composite, images, draft,
                                 focus_layers=args.focus_layer)
    digest = publish_report(args.state_root, manifest['dataset_id'], 'layer-binding-candidates-v2', document)
    read_layer_bindings(args.state_root, manifest, digest, workspace=args.workspace)
    draft_sha = publish_report(args.state_root, manifest['dataset_id'], 'layer-binding-drafts-v2', draft)
    read_layer_binding_draft(args.state_root, manifest, draft_sha, workspace=args.workspace)
    export_document(args.draft_output, draft)
    export_html(args.html, html)
    return document, 'layer-binding-candidates-v2', manifest['dataset_id'], 0
