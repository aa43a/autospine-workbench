"""Verified PSD-local semantic review without manufacturing mapping approval."""

from pathlib import Path

from ..resolved_project import canonical_sha256
from ..safe_input_files import strict_json_object
from .artifacts import publish_report, read_input, read_report
from .mapping_cli import _png_canvas, _read_asset, export_html, load_review_inputs


def register_parser(sub):
    cmd = sub.add_parser("semantic-review", help="Review development PSD layer semantics")
    for name in ("manifest", "evidence", "workspace", "html"):
        cmd.add_argument("--" + name, required=True, type=Path)
    cmd.add_argument("--character", required=True)
    cmd.add_argument("--draft", type=Path)
    cmd.add_argument("--draft-output", type=Path)
    cmd.add_argument("--output", type=Path)


def load_semantic_inputs(manifest, evidence, workspace, selector):
    from .semantic_candidates import build_semantic_candidates

    mapping, _, composite = load_review_inputs(manifest, evidence, workspace, selector)
    record = next(row for row in evidence["characters"] if row["character_id"] == mapping["character_id"]
                  and row["source_psd"] == mapping["psd_source"])
    audit = strict_json_object(_read_asset(workspace, record["outputs"]["audit"]), "semantic audit")
    candidate = build_semantic_candidates(manifest, evidence, mapping["character_id"], audit)
    images = {}
    for row in candidate["layers"]:
        raw = _read_asset(workspace, row["image"])
        bbox = row["bbox"]
        expected = [max(1, bbox[2] - bbox[0]), max(1, bbox[3] - bbox[1])]
        if _png_canvas(raw) != expected:
            raise ValueError("benchmark_semantic_layer_canvas_mismatch")
        images[row["layer_id"]] = raw
    return candidate, audit, composite, images


def read_semantic_candidate(state_root, manifest, digest):
    from .semantic_candidates import validate_semantic_candidates

    dataset = manifest["dataset_id"]
    candidate = read_report(state_root, dataset, "semantic-candidates", digest)
    evidence = read_report(state_root, dataset, "semantic-evidence", candidate["evidence_sha256"])
    snapshot = read_report(state_root, dataset, "semantic-audits", candidate["audit_envelope_sha256"])
    audit = snapshot["payload"]
    return validate_semantic_candidates(manifest, evidence, candidate, audit)


def execute(args):
    from .semantic_draft import build_semantic_draft, validate_semantic_draft
    from .semantic_view import render_semantic_review
    from .artifacts import export_document

    manifest, evidence = read_input(args.manifest), read_input(args.evidence)
    candidate, audit, composite, images = load_semantic_inputs(manifest, evidence, args.workspace, args.character)
    draft = validate_semantic_draft(candidate, read_input(args.draft)) if args.draft else build_semantic_draft(candidate)
    snapshot = {"schema": "autospine.benchmark-audit-snapshot/v1", "authority": "none", "payload": audit}
    for kind, value in (("semantic-evidence", evidence), ("semantic-audits", snapshot),
                        ("semantic-candidates", candidate), ("semantic-drafts", draft)):
        publish_report(args.state_root, manifest["dataset_id"], kind, value)
    read_semantic_candidate(args.state_root, manifest, canonical_sha256(candidate))
    if args.draft_output:
        export_document(args.draft_output, draft)
    export_html(args.html, render_semantic_review(candidate, composite, images, draft=draft))
    return candidate, "semantic-candidates", manifest["dataset_id"], 0
