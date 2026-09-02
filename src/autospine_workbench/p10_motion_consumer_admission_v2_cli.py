"""Automatic exact-address CLI for P10.6a v2 admission."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .p10_capture_job_store import P10CaptureJobStore
from .p10_motion_consumer_admission_commands_v2 import (
    P10MotionConsumerAdmissionCommandV2Error,
    compile_body_sway_motion_consumer_admission_v2_command,
)
from .project_store import ProjectStore, ProjectStoreError


COMMAND = "compile-body-sway-motion-consumer-admission-v2"
ERROR_CODE = "body_sway_motion_consumer_admission_v2_failed"
ERROR_MESSAGE = "Body-sway motion-consumer admission v2 failed."


class _ReadOnlyCaptureJobs:
    def __init__(self, state_root: Path) -> None:
        self._store = P10CaptureJobStore(state_root)

    def get(self, job_id: str) -> dict[str, Any]:
        return self._store.load(job_id).public_document()


def add_p10_motion_consumer_admission_v2_subcommands(
    subparsers: Any,
    default_state_root: Path,
) -> None:
    """Register P10.6a v2 without any file-selection argument."""

    parser = subparsers.add_parser(
        COMMAND,
        help="Admit one exact P10.5d v2 bundle for setup-local consumers",
    )
    parser.add_argument("project_id", metavar="PROJECT")
    parser.add_argument("--dynamic-seam-probe-sha256", required=True)
    parser.add_argument("--dynamic-seam-bundle-sha256", required=True)
    parser.add_argument(
        "--workspace", type=Path,
        default=Path(default_state_root).parent.parent,
    )
    parser.add_argument(
        "--state-root", type=Path, default=Path(default_state_root),
    )


def dispatch_p10_motion_consumer_admission_v2_command(
    args: argparse.Namespace,
) -> int | None:
    """Dispatch with canonical success output and redacted failures."""

    if getattr(args, "command", None) != COMMAND:
        return None
    try:
        store = ProjectStore(args.workspace, state_root=args.state_root)
        result = compile_body_sway_motion_consumer_admission_v2_command(
            _ReadOnlyCaptureJobs(store.state_root), store,
            args.project_id,
            dynamic_seam_probe_sha256=args.dynamic_seam_probe_sha256,
            dynamic_seam_bundle_sha256=args.dynamic_seam_bundle_sha256,
        )
    except _FAILURES:
        _print({
            "error_code": ERROR_CODE,
            "message": ERROR_MESSAGE,
            "ok": False,
            "status": "error",
        })
        return 2
    payload = result.document
    payload.update(ok=True, status="compiled")
    _print(payload)
    return 0


def _print(value: dict[str, Any]) -> None:
    print(json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ))


_FAILURES = (
    OSError, P10MotionConsumerAdmissionCommandV2Error,
    ProjectStoreError, RuntimeError, TypeError, UnicodeError, ValueError,
)


__all__ = [
    "COMMAND", "ERROR_CODE",
    "add_p10_motion_consumer_admission_v2_subcommands",
    "dispatch_p10_motion_consumer_admission_v2_command",
]
