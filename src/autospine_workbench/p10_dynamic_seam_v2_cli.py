"""CLI adapter for exact-address P10.5d v2 compile and verification."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .p10_capture_job_store import (
    P10CaptureJobStore,
    P10CaptureJobStoreError,
)
from .p10_dynamic_seam_commands_v2 import (
    P10DynamicSeamCommandV2Error,
    compile_body_sway_dynamic_seam_probe_v2_command,
    verify_body_sway_dynamic_seam_bundle_v2_command,
)
from .project_store import ProjectStore, ProjectStoreError


COMPILE_COMMAND = "compile-body-sway-dynamic-seam-probe-v2"
VERIFY_COMMAND = "verify-body-sway-dynamic-seam-bundle-v2"
ERROR_CODE = "body_sway_dynamic_seam_v2_failed"
ERROR_MESSAGE = "Body-sway dynamic seam v2 operation failed."


class _ReadOnlyCaptureJobs:
    def __init__(self, state_root: Path) -> None:
        self._store = P10CaptureJobStore(state_root)

    def get(self, job_id: str) -> dict[str, Any]:
        return self._store.load(job_id).public_document()


def add_p10_dynamic_seam_v2_subcommands(
    subparsers: Any, default_state_root: Path,
) -> None:
    compile_parser = subparsers.add_parser(
        COMPILE_COMMAND,
        help="Compile and publish exact P10.5d v2 structural seam evidence",
    )
    compile_parser.add_argument("project_id", metavar="PROJECT")
    compile_parser.add_argument("safety_run_id", metavar="P10_4B_V2_RUN_ID")
    compile_parser.add_argument(
        "--continuous-proof-sha256", required=True,
    )
    compile_parser.add_argument("--reviewed-set-sha256", required=True)
    compile_parser.add_argument(
        "--reviewed-set-bundle-sha256", required=True,
    )
    compile_parser.add_argument(
        "--workspace", type=Path,
        default=Path(default_state_root).parent.parent,
    )
    compile_parser.add_argument(
        "--state-root", type=Path, default=Path(default_state_root),
    )
    verify_parser = subparsers.add_parser(
        VERIFY_COMMAND,
        help="Verify one exact historical P10.5d v2 immutable bundle",
    )
    verify_parser.add_argument("project_id", metavar="PROJECT")
    verify_parser.add_argument("--probe-sha256", required=True)
    verify_parser.add_argument("--bundle-sha256", required=True)
    verify_parser.add_argument(
        "--state-root", type=Path, default=Path(default_state_root),
    )


def dispatch_p10_dynamic_seam_v2_command(
    args: argparse.Namespace,
) -> int | None:
    command = getattr(args, "command", None)
    if command not in {COMPILE_COMMAND, VERIFY_COMMAND}:
        return None
    try:
        if command == COMPILE_COMMAND:
            store = ProjectStore(args.workspace, state_root=args.state_root)
            result = compile_body_sway_dynamic_seam_probe_v2_command(
                _ReadOnlyCaptureJobs(store.state_root),
                store,
                args.project_id,
                args.safety_run_id,
                continuous_proof_sha256=args.continuous_proof_sha256,
                reviewed_set_sha256=args.reviewed_set_sha256,
                reviewed_set_bundle_sha256=(
                    args.reviewed_set_bundle_sha256
                ),
            )
        else:
            result = verify_body_sway_dynamic_seam_bundle_v2_command(
                args.state_root,
                args.project_id,
                probe_sha256=args.probe_sha256,
                bundle_sha256=args.bundle_sha256,
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
    payload["ok"] = True
    _print(payload)
    return 0


def _print(value: dict[str, Any]) -> None:
    print(json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ))


_FAILURES = (
    KeyError, OSError, P10CaptureJobStoreError,
    P10DynamicSeamCommandV2Error, ProjectStoreError,
    RuntimeError, TypeError, UnicodeError, ValueError,
)


__all__ = [
    "COMPILE_COMMAND", "VERIFY_COMMAND",
    "add_p10_dynamic_seam_v2_subcommands",
    "dispatch_p10_dynamic_seam_v2_command",
]
