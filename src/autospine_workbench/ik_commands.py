"""CLI orchestration for exact P4 IK compilation and verification."""

from __future__ import annotations

import argparse
from collections.abc import Mapping
import json
from pathlib import Path
from typing import Any

from .ik_bundle_reader import VerifiedIkBundleReader, VerifiedIkBundleReaderError
from .ik_bundle_store import IkBundleStore, IkBundleStoreError
from .ik_pipeline import VerifiedIkPipeline, VerifiedIkPipelineError
from .ik_target_geometry import SOURCE_IDENTITY_FIELDS


class IkCommandError(RuntimeError):
    """Raised when adjacent verified P4 stages disagree on an identity."""


def add_ik_subcommands(subparsers: Any, *, default_state_root: Path) -> None:
    compile_parser = subparsers.add_parser(
        "compile-ik-targets",
        help="Compile, publish, and fully verify exact P4 IK targets",
    )
    _arguments(compile_parser, default_state_root, compile_command=True)
    verify_parser = subparsers.add_parser(
        "verify-ik-bundle",
        help="Read-only verification of one exact P4 IK bundle address",
    )
    _arguments(verify_parser, default_state_root, compile_command=False)


def compile_ik_targets_command(
    project_id: str,
    state_root: Path,
    *,
    p3_rig_sha256: str,
    p3_bundle_sha256: str,
) -> int:
    """Build from one exact P3 address, publish, then fully read back P4."""
    try:
        pipeline = VerifiedIkPipeline(state_root).build(
            project_id, p3_rig_sha256, p3_bundle_sha256
        )
        inputs, outputs = pipeline.input_sha256s, pipeline.output_sha256s
        _require_pipeline(
            pipeline, inputs, outputs, project_id, p3_rig_sha256, p3_bundle_sha256
        )
        published = IkBundleStore(state_root).publish(
            project_id, pipeline.profile, pipeline.probes
        )
        if published.profile_sha256 != outputs["profile_sha256"]:
            raise IkCommandError("Published IK profile differs from the pipeline")
        verified = VerifiedIkBundleReader(state_root).load(
            project_id, published.profile_sha256, published.bundle_sha256
        )
        _require_verified(
            verified,
            project=project_id,
            inputs=inputs,
            profile_sha=outputs["profile_sha256"],
            probes_sha=outputs["probes_sha256"],
            bundle_sha=published.bundle_sha256,
            p3_rig_sha=p3_rig_sha256,
            p3_bundle_sha=p3_bundle_sha256,
            path=published.path,
        )
        if _summary(verified) != pipeline.summary:
            raise IkCommandError("Verified IK summary differs from the pipeline")
        response = _response(verified)
        response.update(ok=True, status="passed")
    except _DOMAIN_ERRORS as exc:
        _print({"ok": False, "status": "error", "error": str(exc)})
        return 2
    _print(response)
    return 0


def verify_ik_bundle_command(
    project_id: str,
    state_root: Path,
    *,
    profile_sha256: str,
    bundle_sha256: str,
) -> int:
    """Fully verify only the requested immutable P4 address without writes."""
    try:
        verified = VerifiedIkBundleReader(state_root).load(
            project_id, profile_sha256, bundle_sha256
        )
        _require_verified(
            verified,
            project=project_id,
            profile_sha=profile_sha256,
            bundle_sha=bundle_sha256,
        )
        response = _response(verified)
        response.update(ok=True, status="passed")
    except _DOMAIN_ERRORS as exc:
        _print({"ok": False, "status": "error", "error": str(exc)})
        return 2
    _print(response)
    return 0


def _require_pipeline(pipeline, inputs, outputs, project, p3_rig, p3_bundle):
    if not isinstance(inputs, Mapping) or set(inputs) != set(SOURCE_IDENTITY_FIELDS):
        raise IkCommandError("IK pipeline P3 identity inventory is invalid")
    if pipeline.project_id != project or pipeline.summary != "handles=4":
        raise IkCommandError("IK pipeline project or summary is invalid")
    if inputs["rig_sha256"] != p3_rig or inputs["bundle_sha256"] != p3_bundle:
        raise IkCommandError("IK pipeline exact P3 address differs from the request")
    if not isinstance(outputs, Mapping) or set(outputs) != {
        "profile_sha256", "probes_sha256"
    }:
        raise IkCommandError("IK pipeline output identities are invalid")


def _require_verified(verified, *, project, profile_sha, bundle_sha,
                      inputs=None, probes_sha=None, p3_rig_sha=None,
                      p3_bundle_sha=None, path=None) -> None:
    expected = {
        "project_id": project, "profile_sha256": profile_sha,
        "bundle_sha256": bundle_sha,
    }
    optional = {
        "probes_sha256": probes_sha, "p3_rig_sha256": p3_rig_sha,
        "p3_bundle_sha256": p3_bundle_sha,
    }
    expected.update({key: value for key, value in optional.items() if value is not None})
    for field, value in expected.items():
        if getattr(verified, field, None) != value:
            raise IkCommandError(f"Verified IK {field} differs from the request")
    if path is not None and Path(verified.path).resolve() != Path(path).resolve():
        raise IkCommandError("Verified IK path differs from publication")
    source = verified.source_identities
    if not isinstance(source, Mapping) or set(source) != set(SOURCE_IDENTITY_FIELDS):
        raise IkCommandError("Verified IK P3 identity inventory is invalid")
    if inputs is not None:
        for field in SOURCE_IDENTITY_FIELDS:
            if source.get(field) != inputs.get(field):
                raise IkCommandError(f"Verified IK P3 {field} differs from the pipeline")


def _summary(verified) -> str:
    profile, probes = verified.profile, verified.probes
    handles = profile.get("handles") if isinstance(profile, Mapping) else None
    if not isinstance(handles, list) or len(handles) != 4 or \
            not isinstance(probes, Mapping) or probes.get("status") != "passed":
        raise IkCommandError("Verified IK handle inventory or probes are invalid")
    return "handles=4"


def _response(verified) -> dict[str, Any]:
    return {
        "project_id": verified.project_id,
        "p3_source": dict(verified.source_identities),
        "profile_sha256": verified.profile_sha256,
        "probes_sha256": verified.probes_sha256,
        "bundle_sha256": verified.bundle_sha256,
        "path": str(verified.path),
        "summary": _summary(verified),
    }


def _arguments(parser: argparse.ArgumentParser, state_root: Path,
               *, compile_command: bool) -> None:
    parser.add_argument("project_id", help="Audit project identifier")
    if compile_command:
        parser.add_argument("--p3-rig-sha256", required=True)
        parser.add_argument("--p3-bundle-sha256", required=True)
    else:
        parser.add_argument("--profile-sha256", required=True)
        parser.add_argument("--bundle-sha256", required=True)
    parser.add_argument("--state-root", type=Path, default=state_root)


def _print(value: dict[str, Any]) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


_DOMAIN_ERRORS = (
    IkCommandError,
    IkBundleStoreError,
    VerifiedIkBundleReaderError,
    VerifiedIkPipelineError,
)
