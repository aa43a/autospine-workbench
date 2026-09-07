"""Source-bound region binding suggestions over reviewed skeleton candidates."""
from pathlib import Path

from ..resolved_project import canonical_sha256
from .artifacts import read_input, read_report, publish_report, export_document
from .assisted_skeleton_cli import read_assisted_skeleton, _source
from .semantic_cli import load_semantic_inputs
from .mapping_cli import export_html


def register_parser(sub):
    cmd = sub.add_parser('build-region-bindings', help='Preview layer binding options over a reviewed skeleton')
    for name in ('manifest', 'workspace', 'skeleton', 'html'):
        cmd.add_argument('--' + name, required=True, type=Path)
    cmd.add_argument('--output', type=Path)
    cmd.add_argument('--draft', type=Path)
    cmd.add_argument('--draft-output', type=Path)


def sources(state_root, manifest, digest, workspace):
    skeleton = read_assisted_skeleton(state_root, manifest, digest, workspace=workspace)
    candidate, assisted, composite = _source(state_root, manifest, skeleton['source_assisted_sha256'], workspace)
    evidence = read_report(state_root, manifest['dataset_id'], 'semantic-evidence', candidate['evidence_sha256'])
    fresh, _, _, images = load_semantic_inputs(manifest, evidence, workspace, candidate['character_id'])
    if canonical_sha256(fresh) != canonical_sha256(candidate):
        raise ValueError('region_binding_source_changed')
    return candidate, assisted, skeleton, composite, images


def read_region_bindings(state_root, manifest, digest, *, workspace):
    from ..asset.joints.region_binding import validate_region_bindings
    doc = read_report(state_root, manifest['dataset_id'], 'region-binding-candidates', digest)
    candidate, assisted, skeleton, _, _ = sources(state_root, manifest, doc['source_skeleton_sha256'], workspace)
    return validate_region_bindings(candidate, assisted, skeleton, doc)


def execute(args):
    from ..asset.joints.region_binding import build_region_bindings
    from .region_binding_view import render_region_bindings
    from .region_binding_draft import build_binding_draft, validate_binding_draft
    manifest = read_input(args.manifest)
    candidate, assisted, skeleton, composite, images = sources(
        args.state_root, manifest, canonical_sha256(read_input(args.skeleton)), args.workspace)
    doc = build_region_bindings(candidate, assisted, skeleton)
    draft = validate_binding_draft(doc, read_input(args.draft)) if args.draft else build_binding_draft(doc)
    html = render_region_bindings(candidate, assisted, skeleton, doc, composite, images, draft=draft)
    digest = publish_report(args.state_root, manifest['dataset_id'], 'region-binding-candidates', doc)
    read_region_bindings(args.state_root, manifest, digest, workspace=args.workspace)
    draft_digest = publish_report(args.state_root, manifest['dataset_id'], 'region-binding-drafts', draft)
    read_binding_draft(args.state_root, manifest, draft_digest, workspace=args.workspace)
    if args.draft_output:
        export_document(args.draft_output, draft)
    export_html(args.html, html)
    return doc, 'region-binding-candidates', manifest['dataset_id'], 2 if doc['status'] == 'blocked' else 0


def read_binding_draft(state_root, manifest, digest, *, workspace):
    from .region_binding_draft import validate_binding_draft
    draft = read_report(state_root, manifest['dataset_id'], 'region-binding-drafts', digest)
    bindings = read_region_bindings(state_root, manifest, draft['source_bindings_sha256'], workspace=workspace)
    return validate_binding_draft(bindings, draft)
