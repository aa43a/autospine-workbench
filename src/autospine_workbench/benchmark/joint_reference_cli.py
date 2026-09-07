"""Explicit benchmark reference recording, separate from production authority."""
from pathlib import Path
from ..resolved_project import canonical_sha256
from .artifacts import read_input, read_report, publish_report
from .semantic_cli import load_semantic_inputs, publish_semantic_candidate, read_semantic_candidate


def register_parser(sub):
    cmd = sub.add_parser('record-joint-reference', help='Record independently reviewed benchmark joints')
    for name in ('manifest', 'evidence', 'workspace', 'draft'):
        cmd.add_argument('--' + name, required=True, type=Path)
    cmd.add_argument('--character', required=True)
    cmd.add_argument('--reviewer', required=True)
    cmd.add_argument('--confirm-human-review', action='store_true')
    cmd.add_argument('--confirm-independent-annotation', action='store_true')
    cmd.add_argument('--output', type=Path)


def read_joint_reference(state_root, manifest, digest, *, workspace):
    from .joint_reference import validate_joint_reference
    dataset = manifest['dataset_id']
    reference = read_report(state_root, dataset, 'joint-references', digest)
    candidate = read_semantic_candidate(state_root, manifest, reference['source_candidate_sha256'])
    evidence = read_report(state_root, dataset, 'semantic-evidence', candidate['evidence_sha256'])
    fresh, *_ = load_semantic_inputs(manifest, evidence, workspace, candidate['character_id'])
    if canonical_sha256(fresh) != canonical_sha256(candidate):
        raise ValueError('benchmark_reference_source_changed')
    draft = read_report(state_root, dataset, 'joint-drafts', reference['source_draft_sha256'])
    request = read_report(state_root, dataset, 'joint-reference-requests', reference['source_request_sha256'])
    return validate_joint_reference(candidate, draft, request, reference)


def execute(args):
    from .joint_reference import build_joint_reference
    if not args.confirm_human_review or not args.confirm_independent_annotation:
        raise ValueError('benchmark_joint_reference_explicit_review_required')
    manifest, evidence = read_input(args.manifest), read_input(args.evidence)
    candidate, audit, *_ = load_semantic_inputs(manifest, evidence, args.workspace, args.character)
    draft = read_input(args.draft)
    request = {'schema': 'autospine.benchmark-joint-reference-request/v1', 'authority': 'none',
               'candidate_sha256': canonical_sha256(candidate), 'draft_sha256': canonical_sha256(draft),
               'reviewer': args.reviewer, 'decision': 'accept', 'independent_annotation': True}
    reference = build_joint_reference(candidate, draft, request)
    publish_semantic_candidate(args.state_root, manifest, evidence, candidate, audit)
    for kind, doc in (('joint-drafts', draft), ('joint-reference-requests', request), ('joint-references', reference)):
        publish_report(args.state_root, manifest['dataset_id'], kind, doc)
    read_joint_reference(args.state_root, manifest, canonical_sha256(reference), workspace=args.workspace)
    return reference, 'joint-references', manifest['dataset_id'], 0
