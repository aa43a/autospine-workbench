"""PSD-local joint drafts and explicit semantic decision entry points."""

from pathlib import Path

from ..resolved_project import canonical_sha256
from .artifacts import publish_report, read_input, read_report
from .mapping_cli import export_html
from .semantic_cli import load_semantic_inputs, publish_semantic_candidate, read_semantic_candidate


def register_parsers(sub):
    for name in ("joint-review", "record-semantic-review"):
        cmd = sub.add_parser(name)
        for field in ("manifest", "evidence", "workspace"):
            cmd.add_argument("--" + field, required=True, type=Path)
        cmd.add_argument("--character", required=True)
        cmd.add_argument("--draft", type=Path, required=name == "record-semantic-review")
        cmd.add_argument("--output", type=Path)
        if name == "joint-review":
            cmd.add_argument("--html", required=True, type=Path)
            cmd.add_argument("--pose-observations", type=Path)
        else:
            cmd.add_argument("--candidate", required=True, type=Path)
            cmd.add_argument("--request", required=True, type=Path)
            cmd.add_argument("--confirm-human-review", action="store_true")


def read_semantic_decision(state_root, manifest, digest):
    from .semantic_decision import validate_semantic_decision

    dataset = manifest["dataset_id"]
    decision = read_report(state_root, dataset, "semantic-decisions", digest)
    candidate = read_semantic_candidate(state_root, manifest, decision["source_candidate_sha256"])
    draft = read_report(state_root, dataset, "semantic-drafts", decision["source_draft_sha256"])
    request = read_report(state_root, dataset, "semantic-review-requests", decision["source_request_sha256"])
    return validate_semantic_decision(candidate, draft, request, decision)


def read_joint_draft(state_root, manifest, digest):
    from .joint_draft import validate_joint_draft

    draft = read_report(state_root, manifest["dataset_id"], "joint-drafts", digest)
    candidate = read_semantic_candidate(state_root, manifest, draft["candidate_sha256"])
    return validate_joint_draft(candidate, draft)


def execute(args):
    if args.command == "record-semantic-review" and not args.confirm_human_review:
        raise ValueError("benchmark_semantic_human_confirmation_required")
    manifest, evidence = read_input(args.manifest), read_input(args.evidence)
    candidate, audit, composite, _ = load_semantic_inputs(manifest, evidence, args.workspace, args.character)
    dataset = manifest["dataset_id"]
    if args.command == "joint-review":
        if args.pose_observations is not None:
            from .assisted_joint_cli import execute_assisted
            return execute_assisted(args, manifest, evidence, candidate, audit, composite)
        from .joint_draft import build_joint_draft, validate_joint_draft
        from .joint_view import render_joint_review

        draft = validate_joint_draft(candidate, read_input(args.draft)) if args.draft else build_joint_draft(candidate)
        html = render_joint_review(candidate, composite, draft=draft)
        publish_semantic_candidate(args.state_root, manifest, evidence, candidate, audit)
        digest = publish_report(args.state_root, dataset, "joint-drafts", draft)
        read_joint_draft(args.state_root, manifest, digest)
        export_html(args.html, html)
        return draft, "joint-drafts", dataset, 0
    from .semantic_decision import build_semantic_decision

    supplied = read_input(args.candidate)
    if canonical_sha256(supplied) != canonical_sha256(candidate):
        raise ValueError("benchmark_semantic_candidate_mismatch")
    draft, request = read_input(args.draft), read_input(args.request)
    decision = build_semantic_decision(candidate, draft, request)
    publish_semantic_candidate(args.state_root, manifest, evidence, candidate, audit)
    for kind, value in (("semantic-drafts", draft), ("semantic-review-requests", request), ("semantic-decisions", decision)):
        publish_report(args.state_root, dataset, kind, value)
    read_semantic_decision(args.state_root, manifest, canonical_sha256(decision))
    return decision, "semantic-decisions", dataset, 0
