"""Compile a preview from exact user-edited annotations, without modifying Pose."""
from pathlib import Path

from ..resolved_project import canonical_sha256
from .artifacts import read_input, read_report, publish_report
from .assisted_joint_cli import read_assisted_joint_draft
from .semantic_cli import read_semantic_candidate, load_semantic_inputs
from .mapping_cli import export_html


def register_parser(sub):
    cmd = sub.add_parser('build-assisted-skeleton', help='Build a candidate skeleton from reviewed model-assisted annotations')
    for name in ('manifest', 'workspace', 'draft', 'html'):
        cmd.add_argument('--' + name, required=True, type=Path)
    cmd.add_argument('--output', type=Path)


def _source(state_root, manifest, digest, workspace):
    assisted = read_assisted_joint_draft(state_root, manifest, digest, workspace=workspace)
    candidate = read_semantic_candidate(state_root, manifest, assisted['candidate_sha256'])
    evidence = read_report(state_root, manifest['dataset_id'], 'semantic-evidence', candidate['evidence_sha256'])
    fresh, _, composite, _ = load_semantic_inputs(manifest, evidence, workspace, candidate['character_id'])
    if canonical_sha256(candidate) != canonical_sha256(fresh):
        raise ValueError('assisted_skeleton_source_changed')
    return candidate, assisted, composite


def read_assisted_skeleton(state_root, manifest, digest, *, workspace):
    from ..asset.joints.reviewed_skeleton import validate_reviewed_skeleton
    doc = read_report(state_root, manifest['dataset_id'], 'assisted-skeleton-candidates', digest)
    candidate, assisted, _ = _source(state_root, manifest, doc['source_assisted_sha256'], workspace)
    return validate_reviewed_skeleton(candidate, assisted, doc)


def execute(args):
    from ..asset.joints.reviewed_skeleton import build_reviewed_skeleton
    from .assisted_skeleton_view import render_assisted_skeleton
    manifest = read_input(args.manifest)
    candidate, assisted, composite = _source(args.state_root, manifest, canonical_sha256(read_input(args.draft)), args.workspace)
    doc = build_reviewed_skeleton(candidate, assisted)
    html = render_assisted_skeleton(candidate, assisted, doc, composite)
    digest = publish_report(args.state_root, manifest['dataset_id'], 'assisted-skeleton-candidates', doc)
    read_assisted_skeleton(args.state_root, manifest, digest, workspace=args.workspace)
    export_html(args.html, html)
    return doc, 'assisted-skeleton-candidates', manifest['dataset_id'], 0 if doc['status'] == 'candidate_requires_review' else 2
