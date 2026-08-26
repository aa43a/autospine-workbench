"""Canonical CLI adapter for the shared P10.3c visual-review service."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .body_sway_visual_review_address import (
    ExactVisualReviewAddress,
    ExactVisualReviewAddressError,
)
from .body_sway_visual_review_application import (
    BodySwayVisualReviewApplication,
    BodySwayVisualReviewApplicationError,
)
from .body_sway_visual_review_history import BodySwayVisualReviewRevisionConflict
from .body_sway_visual_review_profile import (
    MAX_VISUAL_REVIEW_DOCUMENT_BYTES,
)
from .safe_input_files import SafeInputFileError, read_real_file, strict_json_object


PREPARE_COMMAND = "prepare-body-sway-visual-review"
SUBMIT_COMMAND = "submit-body-sway-visual-review"
PREPARE_ERROR_CODE = "body_sway_visual_review_prepare_failed"
SUBMIT_ERROR_CODE = "body_sway_visual_review_submit_failed"
CONFLICT_ERROR_CODE = "body_sway_visual_review_revision_conflict"


def add_p10_visual_review_subcommands(
    subparsers: Any, default_state_root: Path,
) -> None:
    """Register exact-address preparation and submission commands."""

    prepare = subparsers.add_parser(
        PREPARE_COMMAND,
        help="Prepare exact body-sway still evidence for human review",
    )
    _address_arguments(prepare, default_state_root)
    prepare.add_argument(
        "--document-only", action="store_true",
        help="Print the complete candidate and bounded history snapshot",
    )
    submit = subparsers.add_parser(
        SUBMIT_COMMAND,
        help="Submit one exhaustive body-sway still review revision",
    )
    _address_arguments(submit, default_state_root)
    submit.add_argument("--submission", type=Path, required=True)


def dispatch_p10_visual_review_command(
    args: argparse.Namespace,
) -> int | None:
    """Dispatch visual review without exposing filesystem or exception details."""

    command = getattr(args, "command", None)
    if command not in {PREPARE_COMMAND, SUBMIT_COMMAND}:
        return None
    try:
        address = _address(args)
        service = BodySwayVisualReviewApplication(args.state_root)
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
    except BodySwayVisualReviewRevisionConflict as exc:
        _print({
            "error_code": CONFLICT_ERROR_CODE,
            "message": "Visual review revision is stale; reload exact history.",
            "ok": False,
            "status": "conflict",
            "requested_revision": exc.requested_revision,
            "current_revision": exc.current_revision,
            "requested_head_decision_sha256": exc.requested_head,
            "current_head_decision_sha256": exc.current_head,
        })
        return 3
    except _CLI_ERRORS:
        code = PREPARE_ERROR_CODE if command == PREPARE_COMMAND \
            else SUBMIT_ERROR_CODE
        _print({
            "error_code": code,
            "message": (
                "Body-sway visual review preparation failed."
                if command == PREPARE_COMMAND
                else "Body-sway visual review submission failed."
            ),
            "ok": False,
            "status": "error",
        })
        return 2


def _address_arguments(parser, default_state_root) -> None:
    parser.add_argument("project_id", metavar="PROJECT")
    parser.add_argument("--temporary-preview-sha256", required=True)
    parser.add_argument("--runtime-capture-bundle-sha256", required=True)
    parser.add_argument("--capture-artifact-set-sha256", required=True)
    parser.add_argument(
        "--state-root", type=Path, default=default_state_root
    )


def _address(args) -> ExactVisualReviewAddress:
    return ExactVisualReviewAddress(
        args.project_id,
        args.temporary_preview_sha256,
        args.runtime_capture_bundle_sha256,
        args.capture_artifact_set_sha256,
    )


def _load_submission(path: Path) -> dict[str, Any]:
    data = read_real_file(
        path, MAX_VISUAL_REVIEW_DOCUMENT_BYTES,
        "Visual review submission",
    )
    return strict_json_object(data, "Visual review submission")


def _prepared_summary(result) -> dict[str, Any]:
    candidate, history = result.candidate_document, result.history
    return {
        "ok": True,
        "status": "prepared",
        "address": result.address.public_document(),
        "candidate": {
            "candidate_sha256": result.candidate_sha256,
            "status": candidate["status"],
            "case_count": candidate["summary"]["case_count"],
            "release_gate": candidate["release_gate"],
        },
        "history": _history_document(history),
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
        "rows": [
            {
                "revision": row.revision,
                "decision_sha256": row.decision_sha256,
                "status": row.status,
            }
            for row in history.rows
        ],
    }


def _submitted_document(result) -> dict[str, Any]:
    return {
        "ok": True,
        "status": result.status,
        "address": result.address.public_document(),
        "candidate_sha256": result.candidate_sha256,
        "decision_sha256": result.decision_sha256,
        "revision": result.revision,
        "release_gate": {
            "status": result.release_gate_status,
            "reason_codes": list(result.release_gate_reason_codes),
        },
        "summary": {
            "case_count": result.case_count,
            "approve_count": result.approve_count,
            "reject_count": result.reject_count,
            "unobservable_count": result.unobservable_count,
        },
        "reused": result.reused,
    }


def _print(value: dict[str, Any]) -> None:
    print(json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ))


_CLI_ERRORS = (
    BodySwayVisualReviewApplicationError,
    ExactVisualReviewAddressError,
    OSError,
    SafeInputFileError,
    TypeError,
    UnicodeError,
    ValueError,
)
