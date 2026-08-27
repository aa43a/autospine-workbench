"""Canonical CLI adapter for P10.5b seam-anchor human review."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .safe_input_files import SafeInputFileError, read_real_file, strict_json_object
from .seam_anchor_review_address import (
    ExactSeamAnchorReviewAddress,
    ExactSeamAnchorReviewAddressError,
)
from .seam_anchor_review_application import (
    SeamAnchorReviewApplication,
    SeamAnchorReviewApplicationError,
)
from .seam_anchor_review_errors import SeamAnchorReviewRevisionConflict
from .seam_anchor_review_profile import (
    MAX_SEAM_ANCHOR_REVIEW_DOCUMENT_BYTES,
)


PREPARE_COMMAND = "prepare-seam-anchor-review"
SUBMIT_COMMAND = "submit-seam-anchor-review"
PREPARE_ERROR_CODE = "seam_anchor_review_prepare_failed"
SUBMIT_ERROR_CODE = "seam_anchor_review_submit_failed"
CONFLICT_ERROR_CODE = "seam_anchor_review_revision_conflict"


def add_seam_anchor_review_subcommands(
    subparsers: Any, default_state_root: Path,
) -> None:
    prepare = subparsers.add_parser(
        PREPARE_COMMAND,
        help="Prepare exact static seam candidates for human review",
    )
    _address_arguments(prepare, default_state_root)
    prepare.add_argument(
        "--document-only", action="store_true",
        help="Print the complete candidate and bounded history snapshot",
    )
    submit = subparsers.add_parser(
        SUBMIT_COMMAND,
        help="Submit one exhaustive seam-anchor review revision",
    )
    _address_arguments(submit, default_state_root)
    submit.add_argument("--submission", type=Path, required=True)


def dispatch_seam_anchor_review_command(
    args: argparse.Namespace,
) -> int | None:
    command = getattr(args, "command", None)
    if command not in {PREPARE_COMMAND, SUBMIT_COMMAND}:
        return None
    try:
        address = _address(args)
        service = SeamAnchorReviewApplication(args.state_root)
        if command == PREPARE_COMMAND:
            result = service.prepare(address)
            _print(
                _prepared_document(result)
                if args.document_only else _prepared_summary(result)
            )
        else:
            result = service.submit(
                address, _load_submission(args.submission)
            )
            _print(_submitted_document(result))
        return 0
    except SeamAnchorReviewRevisionConflict as exc:
        _print({
            "error_code": CONFLICT_ERROR_CODE,
            "message": "Seam-review revision is stale; reload exact history.",
            "ok": False, "status": "conflict",
            "requested_revision": exc.requested_revision,
            "current_revision": exc.current_revision,
            "requested_head_decision_sha256": exc.requested_head,
            "current_head_decision_sha256": exc.current_head,
        })
        return 3
    except _CLI_ERRORS:
        prepare = command == PREPARE_COMMAND
        _print({
            "error_code": PREPARE_ERROR_CODE if prepare else SUBMIT_ERROR_CODE,
            "message": (
                "Seam-anchor review preparation failed."
                if prepare else "Seam-anchor review submission failed."
            ),
            "ok": False, "status": "error",
        })
        return 2


def _address_arguments(parser, default_state_root) -> None:
    parser.add_argument("project_id", metavar="PROJECT")
    parser.add_argument("--layer-manifest-sha256", required=True)
    parser.add_argument("--p3-rig-sha256", required=True)
    parser.add_argument("--p3-bundle-sha256", required=True)
    parser.add_argument("--state-root", type=Path, default=default_state_root)


def _address(args) -> ExactSeamAnchorReviewAddress:
    return ExactSeamAnchorReviewAddress(
        args.project_id, args.layer_manifest_sha256,
        args.p3_rig_sha256, args.p3_bundle_sha256,
    )


def _load_submission(path: Path) -> dict[str, Any]:
    data = read_real_file(
        path, MAX_SEAM_ANCHOR_REVIEW_DOCUMENT_BYTES,
        "Seam-review submission",
    )
    return strict_json_object(data, "Seam-review submission")


def _prepared_summary(result) -> dict[str, Any]:
    candidate = result.candidate_document
    return {
        "ok": True, "status": "prepared",
        "address": result.address.public_document(),
        "candidate": {
            "candidate_sha256": result.candidate_sha256,
            "status": candidate["summary"]["status"],
            "summary": candidate["summary"],
            "release_gate": candidate["release_gate"],
        },
        "history": _history_document(result.history),
    }


def _prepared_document(result) -> dict[str, Any]:
    return {
        "address": result.address.public_document(),
        "candidate_sha256": result.candidate_sha256,
        "candidate": result.candidate_document,
        "history": _history_document(result.history),
    }


def _history_document(history) -> dict[str, Any]:
    return {
        "project_id": history.project_id,
        "candidate_sha256": history.candidate_sha256,
        "revision_count": history.revision_count,
        "current_revision": history.current_revision,
        "head_decision_sha256": history.head_decision_sha256,
        "rows": [{
            "revision": row.revision,
            "decision_sha256": row.decision_sha256,
            "status": row.status,
        } for row in history.rows],
    }


def _submitted_document(result) -> dict[str, Any]:
    return {
        "ok": True, "status": result.status,
        "address": result.address.public_document(),
        "candidate_sha256": result.candidate_sha256,
        "decision_sha256": result.decision_sha256,
        "revision": result.revision,
        "release_gate": {
            "status": result.release_gate_status,
            "reason_codes": list(result.release_gate_reason_codes),
        },
        "summary": {
            "relationship_count": result.relationship_count,
            "accept_count": result.accept_count,
            "adjust_count": result.adjust_count,
            "reject_count": result.reject_count,
            "unobservable_count": result.unobservable_count,
            "anchor_pair_count": result.anchor_pair_count,
        },
        "reused": result.reused,
    }


def _print(value: dict[str, Any]) -> None:
    print(json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ))


_CLI_ERRORS = (
    ExactSeamAnchorReviewAddressError, OSError, SafeInputFileError,
    SeamAnchorReviewApplicationError, TypeError, UnicodeError, ValueError,
)
