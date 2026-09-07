"""Reproducible diagnostic comparison of the legacy baseline and joint drafts."""
from pathlib import Path

from ..resolved_project import canonical_sha256
from .artifacts import export_document, publish_report, read_input, read_report
from .joint_draft import build_joint_draft, validate_joint_draft
from .mapping_cli import export_html
from .semantic_cli import load_semantic_inputs, publish_semantic_candidate, read_semantic_candidate


def register_parser(sub):
    cmd = sub.add_parser('compare-joints', help='Compare legacy joint guesses with an unapproved draft')
    for name in ('manifest', 'evidence', 'workspace', 'html'):
        cmd.add_argument('--' + name, type=Path, required=True)
    cmd.add_argument('--character', required=True)
    cmd.add_argument('--draft', type=Path)
    cmd.add_argument('--baseline-output', type=Path)
    cmd.add_argument('--output', type=Path)


def read_joint_comparison(state_root, manifest, digest, *, workspace):
    from .joint_baseline import validate_joint_baseline
    from .joint_comparison import validate_joint_comparison
    from .joint_comparison_view import composite_height

    dataset = manifest['dataset_id']
    report = read_report(state_root, dataset, 'joint-comparisons', digest)
    candidate = read_semantic_candidate(state_root, manifest, report['source_candidate_sha256'])
    evidence = read_report(state_root, dataset, 'semantic-evidence', candidate['evidence_sha256'])
    fresh, audit, composite, _ = load_semantic_inputs(manifest, evidence, workspace, candidate['character_id'])
    if canonical_sha256(fresh) != canonical_sha256(candidate):
        raise ValueError('benchmark_joint_candidate_mismatch')
    baseline = read_report(state_root, dataset, 'joint-baselines', report['source_baseline_sha256'])
    draft = read_report(state_root, dataset, 'joint-drafts', report['source_draft_sha256'])
    validate_joint_baseline(candidate, audit, baseline)
    return validate_joint_comparison(candidate, baseline, draft, report,
                                     character_height=composite_height(candidate, composite))


def execute(args):
    from .joint_baseline import build_joint_baseline
    from .joint_comparison import build_joint_comparison
    from .joint_comparison_view import composite_height, render_joint_comparison

    manifest, evidence = read_input(args.manifest), read_input(args.evidence)
    candidate, audit, composite, _ = load_semantic_inputs(manifest, evidence, args.workspace, args.character)
    baseline = build_joint_baseline(candidate, audit)
    draft = validate_joint_draft(candidate, read_input(args.draft)) if args.draft else build_joint_draft(candidate)
    report = build_joint_comparison(candidate, baseline, draft, character_height=composite_height(candidate, composite))
    html = render_joint_comparison(candidate, baseline, draft, report, composite)
    publish_semantic_candidate(args.state_root, manifest, evidence, candidate, audit)
    for kind, value in (('joint-baselines', baseline), ('joint-drafts', draft), ('joint-comparisons', report)):
        publish_report(args.state_root, manifest['dataset_id'], kind, value)
    read_joint_comparison(args.state_root, manifest, canonical_sha256(report), workspace=args.workspace)
    if args.baseline_output:
        export_document(args.baseline_output, baseline)
    export_html(args.html, html)
    return report, 'joint-comparisons', manifest['dataset_id'], 0
