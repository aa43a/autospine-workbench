"""Automatic CLI adapters for P10.4a BodySwayReviewAdmission v2."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .body_sway_review_admission_consumer_v2 import (
    BodySwayReviewAdmissionV2ConsumerError,
    require_current_body_sway_review_admission_v2,
)
from .body_sway_review_admission_profile_v2 import (
    MAX_ADMISSION_DOCUMENT_BYTES,
)
from .p10_capture_job_store import P10CaptureJobStore
from .p10_review_admission_v2_commands import (
    P10ReviewAdmissionV2CommandError,
    compile_body_sway_review_admission_v2_for_job,
)
from .project_store import ProjectStore, ProjectStoreError
from .safe_input_files import SafeInputFileError, read_real_file, strict_json_object


COMPILE_COMMAND = "compile-body-sway-review-admission-v2"
VERIFY_COMMAND = "verify-body-sway-review-admission-v2"
ERROR_CODE = "body_sway_review_admission_v2_failed"
ERROR_MESSAGE = "Body-sway review admission v2 failed."


class _ReadOnlyCaptureJobs:
    def __init__(self, state_root: Path) -> None:
        self._store = P10CaptureJobStore(state_root)

    def get(self, job_id: str) -> dict[str, Any]:
        return self._store.load(job_id).public_document()


def add_p10_review_admission_v2_subcommands(
    subparsers: Any, default_state_root: Path,
) -> None:
    default_workspace = Path(default_state_root).parent.parent
    compile_parser = subparsers.add_parser(
        COMPILE_COMMAND,
        help="Auto-admit a completed job's current approved v2 review head",
    )
    compile_parser.add_argument("job_id", metavar="JOB_ID")
    _common(compile_parser, default_state_root, default_workspace)
    compile_parser.add_argument("--expected-candidate-sha256")
    compile_parser.add_argument("--expected-visual-revision", type=int)
    compile_parser.add_argument("--expected-decision-sha256")
    compile_parser.add_argument(
        "--document-only", action="store_true",
        help="Print only the canonical BodySwayReviewAdmission v2 document",
    )

    verify_parser = subparsers.add_parser(
        VERIFY_COMMAND,
        help="Recompile and consume one admission only if it remains current",
    )
    verify_parser.add_argument("admission", type=Path, metavar="ADMISSION_JSON")
    _common(verify_parser, default_state_root, default_workspace)


def dispatch_p10_review_admission_v2_command(
    args: argparse.Namespace,
) -> int | None:
    command = getattr(args, "command", None)
    if command not in {COMPILE_COMMAND, VERIFY_COMMAND}:
        return None
    try:
        store = ProjectStore(args.workspace, state_root=args.state_root)
        jobs = _ReadOnlyCaptureJobs(store.state_root)
        if command == COMPILE_COMMAND:
            result = compile_body_sway_review_admission_v2_for_job(
                jobs, store, args.job_id,
                expected_candidate_sha256=args.expected_candidate_sha256,
                expected_visual_revision=args.expected_visual_revision,
                expected_decision_sha256=args.expected_decision_sha256,
            )
            payload = result.document if args.document_only else _summary(result)
        else:
            raw = read_real_file(
                args.admission, MAX_ADMISSION_DOCUMENT_BYTES,
                "BodySwayReviewAdmission v2",
            )
            document = strict_json_object(
                raw, "BodySwayReviewAdmission v2",
            )
            current = require_current_body_sway_review_admission_v2(
                jobs, store, document,
            )
            payload = {
                "ok": True, "status": "current",
                "job_id": current.job_id,
                "admission_sha256": current.admission_sha256,
                "claims": current.document["claims"],
                "release_gate": current.document["release_gate"],
            }
    except _FAILURES:
        _print({
            "error_code": ERROR_CODE, "message": ERROR_MESSAGE,
            "ok": False, "status": "error",
        })
        return 2
    _print(payload)
    return 0


def _common(parser, state_root, workspace):
    parser.add_argument("--workspace", type=Path, default=workspace)
    parser.add_argument("--state-root", type=Path, default=state_root)


def _summary(result) -> dict[str, Any]:
    return {
        "ok": True,
        "status": result.document["status"],
        "job_id": result.job_id,
        "package_id": result.package_id,
        "project_id": result.project_id,
        "clip_id": result.clip_id,
        "terminal_event_sha256": result.terminal_event_sha256,
        "terminal_sequence": result.terminal_sequence,
        "visual_candidate_sha256": result.visual_candidate_sha256,
        "visual_revision": result.visual_revision,
        "visual_decision_sha256": result.visual_decision_sha256,
        "admission_sha256": result.admission_sha256,
        "claims": result.document["claims"],
        "release_gate": result.document["release_gate"],
    }


def _print(value: dict[str, Any]) -> None:
    print(json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ))


_FAILURES = (
    BodySwayReviewAdmissionV2ConsumerError, OSError,
    P10ReviewAdmissionV2CommandError, ProjectStoreError,
    RuntimeError, SafeInputFileError, TypeError, UnicodeError, ValueError,
)


__all__ = [
    "COMPILE_COMMAND", "VERIFY_COMMAND",
    "add_p10_review_admission_v2_subcommands",
    "dispatch_p10_review_admission_v2_command",
]
