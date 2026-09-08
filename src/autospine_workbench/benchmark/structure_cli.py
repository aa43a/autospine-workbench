"""Source-verified structural triage without modifying selected bindings."""
from pathlib import Path

from ..resolved_project import canonical_sha256
from ..asset.joints.structure_candidates import build_structure_candidates, validate_structure_candidates
from .artifacts import read_input, read_report, publish_report
from .mesh_candidate_cli import inputs
from .mapping_cli import export_html


def register_parser(sub):
    cmd = sub.add_parser('propose-layer-structure', help='Inspect garment and bilateral component candidates')
    for name in ('manifest', 'workspace', 'draft', 'html'):
        cmd.add_argument('--'+name, type=Path, required=True)
    cmd.add_argument('--output', type=Path)


def read_structure(state_root, manifest, digest, *, workspace):
    doc = read_report(state_root, manifest['dataset_id'], 'structure-candidates', digest)
    candidate, assisted, skeleton, bindings, draft, _, images = inputs(
        state_root, manifest, doc['source_draft_sha256'], workspace)
    return validate_structure_candidates(candidate, assisted, skeleton, bindings, draft, images, doc)


def execute(args):
    from .structure_view import render_structure
    manifest = read_input(args.manifest)
    candidate, assisted, skeleton, bindings, draft, composite, images = inputs(
        args.state_root, manifest, canonical_sha256(read_input(args.draft)), args.workspace)
    doc = build_structure_candidates(candidate, assisted, skeleton, bindings, draft, images)
    digest = publish_report(args.state_root, manifest['dataset_id'], 'structure-candidates', doc)
    read_structure(args.state_root, manifest, digest, workspace=args.workspace)
    export_html(args.html, render_structure(candidate, skeleton, bindings, draft, doc, composite, images))
    return doc, 'structure-candidates', manifest['dataset_id'], 0
