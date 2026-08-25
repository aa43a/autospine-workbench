"""CLI orchestration for exact reusable built-in MotionIR bundles."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .motion_builtin import BuiltinMotionError, build_builtin_motion
from .motion_bundle_reader import (
    VerifiedMotionBundleReader,
    VerifiedMotionBundleReaderError,
)
from .motion_bundle_contract import (
    MotionBundleContractError,
    build_motion_bundle_contract,
)
from .motion_bundle_store import MotionBundleStore, MotionBundleStoreError
from .motion_compile_run import (
    MotionCompileRunError,
    build_builtin_motion_compile_run,
)


class MotionCommandError(RuntimeError):
    """Raised when adjacent verified motion stages disagree on identity or bytes."""


def add_motion_subcommands(subparsers: Any, *, default_state_root: Path) -> None:
    compile_parser = subparsers.add_parser(
        "compile-builtin-motion",
        help="Compile, publish, and read back one exact built-in MotionIR bundle",
    )
    compile_parser.add_argument("clip_id", help="Exact built-in clip identifier")
    compile_parser.add_argument(
        "--state-root", type=Path, default=default_state_root,
        help="Root for immutable motion bundles",
    )
    verify_parser = subparsers.add_parser(
        "verify-motion-bundle",
        help="Read-only verification of one exact motion bundle address",
    )
    verify_parser.add_argument("--clip-sha256", required=True)
    verify_parser.add_argument("--bundle-sha256", required=True)
    verify_parser.add_argument(
        "--state-root", type=Path, default=default_state_root,
        help="Root containing immutable motion bundles",
    )


def compile_builtin_motion_command(clip_id: str, state_root: Path) -> int:
    """Build, publish, and reproduce one built-in through the secure reader."""

    try:
        motion = build_builtin_motion(clip_id)
        run = build_builtin_motion_compile_run(clip_id, motion.document)
        contract = build_motion_bundle_contract(motion.document, run.document)
        published = MotionBundleStore(state_root).publish(
            motion.document, run.document
        )
        _require_publication(published, contract, state_root)
        verified = VerifiedMotionBundleReader(state_root).load(
            published.clip_sha256, published.bundle_sha256
        )
        _require_verified(
            verified,
            clip_id=clip_id,
            clip_sha256=published.clip_sha256,
            run_sha256=published.run_sha256,
            bundle_sha256=published.bundle_sha256,
            path=published.path,
            motion_bytes=motion.canonical_json.encode("utf-8"),
            run_bytes=run.canonical_bytes,
        )
        response = _response(verified, reused=published.reused)
        response.update(ok=True, status="passed")
    except _DOMAIN_ERRORS as exc:
        _print({"ok": False, "status": "error", "error": str(exc)})
        return 2
    _print(response)
    return 0


def verify_motion_bundle_command(
    state_root: Path, *, clip_sha256: str, bundle_sha256: str
) -> int:
    """Read and reproduce only the requested immutable address without writes."""

    try:
        verified = VerifiedMotionBundleReader(state_root).load(
            clip_sha256, bundle_sha256
        )
        clip_id = getattr(verified, "clip_id", None)
        if type(clip_id) is not str:
            raise MotionCommandError("Verified motion clip_id is invalid")
        motion = build_builtin_motion(clip_id)
        run = build_builtin_motion_compile_run(clip_id, motion.document)
        contract = build_motion_bundle_contract(motion.document, run.document)
        if contract.clip_sha256 != clip_sha256 \
                or contract.bundle_sha256 != bundle_sha256:
            raise MotionCommandError(
                "Verified motion bytes differ from the exact requested address"
            )
        _require_verified(
            verified,
            clip_id=clip_id,
            clip_sha256=clip_sha256,
            run_sha256=run.sha256,
            bundle_sha256=bundle_sha256,
            path=(
                Path(state_root).resolve() / "motions" / clip_sha256
                / bundle_sha256
            ),
            motion_bytes=motion.canonical_json.encode("utf-8"),
            run_bytes=run.canonical_bytes,
        )
        response = _response(verified, reused=None)
        response.update(ok=True, status="passed")
    except _DOMAIN_ERRORS as exc:
        _print({"ok": False, "status": "error", "error": str(exc)})
        return 2
    _print(response)
    return 0


def _require_publication(published, contract, state_root: Path) -> None:
    expected = {
        "clip_id": contract.clip_id,
        "clip_sha256": contract.clip_sha256,
        "run_sha256": contract.run_sha256,
        "bundle_sha256": contract.bundle_sha256,
    }
    for field, value in expected.items():
        if getattr(published, field, None) != value:
            raise MotionCommandError(
                f"Published motion {field} differs from compilation"
            )
    if type(getattr(published, "reused", None)) is not bool:
        raise MotionCommandError("Published motion reuse status is invalid")
    published_path = getattr(published, "path", None)
    if not isinstance(published_path, Path):
        raise MotionCommandError("Published motion path is invalid")
    expected_path = (
        Path(state_root).resolve() / "motions" / contract.clip_sha256
        / contract.bundle_sha256
    )
    if published_path.resolve() != expected_path:
        raise MotionCommandError("Published motion path differs from its exact address")


def _require_verified(
    verified,
    *,
    clip_id: str,
    clip_sha256: str,
    run_sha256: str,
    bundle_sha256: str,
    motion_bytes: bytes,
    run_bytes: bytes,
    path: Path | None = None,
) -> None:
    expected = {
        "clip_id": clip_id,
        "clip_sha256": clip_sha256,
        "run_sha256": run_sha256,
        "bundle_sha256": bundle_sha256,
    }
    for field, value in expected.items():
        if getattr(verified, field, None) != value:
            raise MotionCommandError(
                f"Verified motion {field} differs from the exact request"
            )
    verified_path = getattr(verified, "path", None)
    if not isinstance(verified_path, Path):
        raise MotionCommandError("Verified motion path is invalid")
    if path is not None and verified_path.resolve() != Path(path).resolve():
        raise MotionCommandError("Verified motion path differs from publication")
    expected_bytes = {
        "motion.json": motion_bytes,
        "run-manifest.json": run_bytes,
    }
    if getattr(verified, "document_bytes", None) != expected_bytes:
        raise MotionCommandError(
            "Verified motion canonical bytes differ from compilation"
        )


def _response(verified, *, reused: bool | None) -> dict[str, Any]:
    return {
        "clip_id": verified.clip_id,
        "clip_sha256": verified.clip_sha256,
        "run_sha256": verified.run_sha256,
        "bundle_sha256": verified.bundle_sha256,
        "path": str(verified.path),
        "reused": reused,
    }


def _print(value: dict[str, Any]) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


_DOMAIN_ERRORS = (
    BuiltinMotionError,
    MotionCommandError,
    MotionBundleContractError,
    MotionBundleStoreError,
    VerifiedMotionBundleReaderError,
    MotionCompileRunError,
)
