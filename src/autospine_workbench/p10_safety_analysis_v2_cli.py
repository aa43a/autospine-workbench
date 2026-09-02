"""Job-only professional CLI for combined P10.4b v2 safety analysis."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .p10_capture_job_store import (
    P10CaptureJobStore, P10CaptureJobStoreError,
)
from .p10_safety_analysis_v2_commands import (
    P10SafetyAnalysisV2CommandError,
    compile_p10_safety_analysis_v2_for_job,
)
from .project_store import ProjectStore, ProjectStoreError


COMPILE_COMMAND = "compile-body-sway-safety-analysis-v2"
ERROR_CODE = "body_sway_safety_analysis_v2_failed"
ERROR_MESSAGE = "Body-sway safety analysis v2 failed."


class _ReadOnlyCaptureJobs:
    def __init__(self, state_root: Path) -> None:
        self._store = P10CaptureJobStore(state_root)

    def get(self, job_id: str) -> dict[str, Any]:
        return self._store.load(job_id).public_document()


def add_p10_safety_analysis_v2_subcommands(
    subparsers: Any, default_state_root: Path,
) -> None:
    parser = subparsers.add_parser(
        COMPILE_COMMAND,
        help="Compile v2 amplitude and continuous proof from one completed job",
    )
    parser.add_argument("job_id", metavar="JOB_ID")
    parser.add_argument(
        "--documents", action="store_true",
        help="Include both canonical v2 documents in the JSON response",
    )
    parser.add_argument(
        "--workspace", type=Path,
        default=Path(default_state_root).parent.parent,
    )
    parser.add_argument(
        "--state-root", type=Path, default=default_state_root,
    )


def dispatch_p10_safety_analysis_v2_command(
    args: argparse.Namespace,
) -> int | None:
    if getattr(args, "command", None) != COMPILE_COMMAND:
        return None
    try:
        store = ProjectStore(args.workspace, state_root=args.state_root)
        jobs = _ReadOnlyCaptureJobs(store.state_root)
        result = compile_p10_safety_analysis_v2_for_job(
            jobs, store, args.job_id,
        )
        payload = _summary(result, include_documents=args.documents)
    except _FAILURES:
        _print({
            "error_code": ERROR_CODE, "message": ERROR_MESSAGE,
            "ok": False, "status": "error",
        })
        return 2
    _print(payload)
    return 0


def _summary(result, *, include_documents: bool) -> dict[str, Any]:
    amplitude = result.amplitude_document
    continuous = result.continuous_document
    payload = {
        "ok": True, "status": result.status,
        "job_id": result.job_id, "package_id": result.package_id,
        "project_id": result.project_id, "clip_id": result.clip_id,
        "admission_sha256": result.admission_sha256,
        "amplitude": {
            "sha256": result.amplitude_sha256,
            "status": amplitude["status"],
            "probe_count": len(amplitude["probes"]),
            "visual_review_scope": "reviewed_gain_only",
        },
        "continuous": {
            "sha256": result.continuous_sha256,
            "status": continuous["status"],
            "summary": continuous["summary"],
        },
        "claims": continuous["claims"],
        "release_gate": continuous["release_gate"],
    }
    if include_documents:
        payload["documents"] = {
            "amplitude": amplitude, "continuous": continuous,
        }
    return payload


def _print(value: dict[str, Any]) -> None:
    print(json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ))


_FAILURES = (
    KeyError, OSError, P10CaptureJobStoreError,
    P10SafetyAnalysisV2CommandError, ProjectStoreError,
    RuntimeError, TypeError, UnicodeError, ValueError,
)


__all__ = [
    "COMPILE_COMMAND", "add_p10_safety_analysis_v2_subcommands",
    "dispatch_p10_safety_analysis_v2_command",
]
