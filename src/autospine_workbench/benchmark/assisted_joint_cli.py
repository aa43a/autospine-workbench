"""Prepare or resume all-point model-assisted annotations without independent GT."""
from ..resolved_project import canonical_sha256
from .artifacts import publish_report, read_input, read_report
from .mapping_cli import export_html
from .pose_contact_cli import ingest_selected_runner
from .semantic_cli import publish_semantic_candidate, read_semantic_candidate, load_semantic_inputs


def read_assisted_joint_draft(state_root, manifest, digest, *, workspace):
    from .joint_baseline import validate_joint_baseline
    from .pose_source import read_pose
    from .assisted_joint_draft import validate_assisted_joint_draft
    dataset = manifest['dataset_id']
    doc = read_report(state_root, dataset, 'assisted-joint-drafts', digest)
    candidate = read_semantic_candidate(state_root, manifest, doc['candidate_sha256'])
    evidence = read_report(state_root, dataset, 'semantic-evidence', candidate['evidence_sha256'])
    fresh, audit, *_ = load_semantic_inputs(manifest, evidence, workspace, candidate['character_id'])
    if canonical_sha256(fresh) != canonical_sha256(candidate):
        raise ValueError('benchmark_assisted_source_changed')
    baseline = read_report(state_root, dataset, 'joint-baselines', doc['source_baseline_sha256'])
    validate_joint_baseline(candidate, audit, baseline)
    pose = read_pose(state_root, candidate, doc['source_pose_sha256'])
    return validate_assisted_joint_draft(candidate, baseline, pose, doc)


def execute_assisted(args, manifest, evidence, candidate, audit, composite):
    from .joint_baseline import build_joint_baseline
    from .joint_view import render_joint_review
    from .assisted_joint_draft import build_assisted_joint_draft, validate_assisted_joint_draft
    pose = ingest_selected_runner(args, candidate, evidence)
    baseline = build_joint_baseline(candidate, audit)
    doc = validate_assisted_joint_draft(candidate, baseline, pose, read_input(args.draft)) if args.draft else \
        build_assisted_joint_draft(candidate, baseline, pose)
    html = render_joint_review(candidate, composite, assistance=doc)
    publish_semantic_candidate(args.state_root, manifest, evidence, candidate, audit)
    publish_report(args.state_root, manifest['dataset_id'], 'joint-baselines', baseline)
    digest = publish_report(args.state_root, manifest['dataset_id'], 'assisted-joint-drafts', doc)
    read_assisted_joint_draft(args.state_root, manifest, digest, workspace=args.workspace)
    export_html(args.html, html)
    return doc, 'assisted-joint-drafts', manifest['dataset_id'], 0
