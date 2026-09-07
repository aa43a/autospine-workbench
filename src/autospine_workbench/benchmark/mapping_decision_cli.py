"""Explicit mapping review recording, separate from candidate generation."""

from pathlib import Path

from ..resolved_project import canonical_sha256
from .artifacts import publish_report, read_input
from .mapping_cli import load_review_inputs


def register_parsers(sub):
    record = sub.add_parser("record-mapping-review", help="Record an explicit human benchmark mapping review")
    for name in ("manifest", "evidence", "workspace", "candidate", "request"):
        record.add_argument("--" + name, required=True, type=Path)
    record.add_argument("--character", required=True)
    record.add_argument("--confirm-human-review", action="store_true")
    record.add_argument("--output", type=Path)
    template = sub.add_parser("annotation-template", help="Prepare pending annotations from an exact accepted mapping")
    template.add_argument("--manifest", required=True, type=Path)
    template.add_argument("--decision", required=True, type=Path)
    template.add_argument("--output", type=Path)


def execute(args):
    from .mapping_decision import build_mapping_decision
    from .mapping_decision_store import read_mapping_decision

    manifest = read_input(args.manifest)
    dataset = manifest["dataset_id"]
    if args.command == "annotation-template":
        from .mapping_annotation import build_annotation_template

        supplied = read_input(args.decision)
        digest = canonical_sha256(supplied)
        decision = read_mapping_decision(args.state_root, manifest, digest)
        return build_annotation_template(manifest, decision), "annotation-drafts", dataset, 0
    if not args.confirm_human_review:
        raise ValueError("benchmark_mapping_human_confirmation_required")
    candidate, _, _ = load_review_inputs(manifest, read_input(args.evidence), args.workspace,
                                         args.character, read_input(args.candidate))
    request = read_input(args.request)
    decision = build_mapping_decision(manifest, candidate, request)
    for kind, value in (("mapping-candidates", candidate), ("mapping-review-requests", request),
                        ("mapping-decisions", decision)):
        publish_report(args.state_root, dataset, kind, value)
    read_mapping_decision(args.state_root, manifest, canonical_sha256(decision))
    return decision, "mapping-decisions", dataset, 0
