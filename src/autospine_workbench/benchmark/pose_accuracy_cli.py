"""Evaluate exact R2-A observations against explicit benchmark references."""
from pathlib import Path
from ..resolved_project import canonical_sha256
from .artifacts import read_input, read_report, publish_report
from .joint_reference_cli import read_joint_reference
from .mapping_cli import export_html
from .r2a_cli import read_r2a
from .semantic_cli import read_semantic_candidate, load_semantic_inputs


def register_parser(sub):
    cmd = sub.add_parser('evaluate-pose-benchmark', help='Compare baseline, pose and optimized joints against independent GT')
    for name in ('manifest', 'workspace', 'run', 'html'):
        cmd.add_argument('--' + name, required=True, type=Path)
    cmd.add_argument('--reference', type=Path)
    cmd.add_argument('--output', type=Path)


def _build(state_root, manifest, run_sha, reference_sha, workspace):
    from .joint_baseline import build_joint_baseline
    from .joint_comparison_view import composite_height
    from .pose_source import read_pose
    from .pose_accuracy import build_pose_accuracy
    dataset = manifest['dataset_id']
    run = read_r2a(state_root, manifest, run_sha, workspace=workspace)
    candidate = read_semantic_candidate(state_root, manifest, run['candidate_sha256'])
    evidence = read_report(state_root, dataset, 'semantic-evidence', candidate['evidence_sha256'])
    fresh, audit, composite, _ = load_semantic_inputs(manifest, evidence, workspace, candidate['character_id'])
    if canonical_sha256(fresh) != canonical_sha256(candidate):
        raise ValueError('benchmark_pose_accuracy_source_changed')
    optimized = read_report(state_root, dataset, 'joint-optimizations', run['optimization_sha256'])
    if optimized['pose_sha256'] is None:
        raise ValueError('pose_observations_required')
    pose = read_pose(state_root, candidate, optimized['pose_sha256'])
    reference = read_joint_reference(state_root, manifest, reference_sha, workspace=workspace) if reference_sha else None
    report = build_pose_accuracy(candidate, build_joint_baseline(candidate, audit), pose, optimized, reference,
                                 character_height=composite_height(candidate, composite))
    return {'schema': 'autospine.benchmark-pose-evaluation/v1', 'authority': 'none',
            'run_sha256': run_sha, 'reference_sha256': reference_sha, 'analysis': report}


def read_pose_evaluation(state_root, manifest, digest, *, workspace):
    doc = read_report(state_root, manifest['dataset_id'], 'pose-evaluations', digest)
    expected = _build(state_root, manifest, doc['run_sha256'], doc['reference_sha256'], workspace)
    if canonical_sha256(expected) != canonical_sha256(doc):
        raise ValueError('benchmark_pose_evaluation_mismatch')
    return expected


def execute(args):
    from .pose_accuracy_view import render_pose_accuracy
    manifest = read_input(args.manifest)
    reference_sha = canonical_sha256(read_input(args.reference)) if args.reference else None
    report = _build(args.state_root, manifest, canonical_sha256(read_input(args.run)), reference_sha, args.workspace)
    html = render_pose_accuracy(report)
    digest = publish_report(args.state_root, manifest['dataset_id'], 'pose-evaluations', report)
    read_pose_evaluation(args.state_root, manifest, digest, workspace=args.workspace)
    export_html(args.html, html)
    return report, 'pose-evaluations', manifest['dataset_id'], 0
