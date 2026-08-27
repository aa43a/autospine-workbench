"""Application commands for P10.7a Spine 4.2 v3 publication."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any

from .manifest_artifacts import require_sha256
from .seam_anchor_review_json import canonical_json_bytes
from .spine42_v3_bundle_files import NAMESPACE
from .spine42_v3_bundle_integrity import VerifiedSpine42V3Bundle
from .spine42_v3_bundle_reader import VerifiedSpine42V3BundleReader
from .spine42_v3_bundle_store import (
    PublishedSpine42V3Bundle,
    Spine42V3BundleStore,
)
from .spine42_v3_current_heads import (
    load_motion_instance_v3_and_dynamic_source,
    observe_spine42_v3_current_heads,
    require_same_spine42_v3_heads,
)
from .spine42_v3_pipeline import VerifiedSpine42V3Pipeline
from .spine42_v3_pipeline_result import VerifiedSpine42V3Compilation


class P10Spine42V3CommandError(RuntimeError):
    """Raised with one fixed, path-free P10.7a failure boundary."""


@dataclass(frozen=True, slots=True)
class P10Spine42V3CommandResult:
    mode: str
    project_id: str
    clip_id: str
    skeleton_json_sha256: str
    bundle_sha256: str
    reused: bool | None
    _canonical_json: str = field(repr=False)

    @property
    def document(self) -> dict[str, Any]:
        return json.loads(self._canonical_json)


def compile_body_sway_spine42_v3_command(
    state_root: Path,
    project_id: str,
    *,
    motion_instance_v3_sha256: str,
    motion_instance_v3_bundle_sha256: str,
) -> P10Spine42V3CommandResult:
    """Compile, publish, read back, and replay under stable review heads."""

    try:
        state = Path(state_root)
        expected_v3 = require_sha256(
            motion_instance_v3_sha256, "MotionInstance v3 digest"
        )
        expected_v3_bundle = require_sha256(
            motion_instance_v3_bundle_sha256,
            "MotionInstance v3 bundle digest",
        )
        motion, source = load_motion_instance_v3_and_dynamic_source(
            state, project_id, expected_v3, expected_v3_bundle
        )
        before = observe_spine42_v3_current_heads(state, source)
        pending = VerifiedSpine42V3Pipeline(state).build(
            project_id, expected_v3, expected_v3_bundle
        )
        _require_motion_source(pending, motion)
        after_compile = observe_spine42_v3_current_heads(state, source)
        require_same_spine42_v3_heads(before, after_compile)
        published = Spine42V3BundleStore(state).publish(
            project_id, expected_v3, expected_v3_bundle
        )
        _require_published(published, pending)
        verified = VerifiedSpine42V3BundleReader(state).load(
            project_id, published.skeleton_json_sha256,
            published.bundle_sha256,
        )
        _require_exact_readback(verified, pending)
        after_readback = observe_spine42_v3_current_heads(state, source)
        require_same_spine42_v3_heads(before, after_readback)
        return _result(
            "compiled", verified, published.reused,
            head_check={
                "scope": "prepublication_compile_and_exact_readback",
                "before_after_identity": "exact_match",
                "before_after_canonical_bytes": "exact_match",
                "current_heads_observed": True,
                "permanent_authority_claimed": False,
            },
        )
    except _COMMAND_FAILURES as exc:
        raise P10Spine42V3CommandError(
            "Body-sway Spine 4.2 v3 compilation failed"
        ) from exc


def verify_body_sway_spine42_v3_command(
    state_root: Path,
    project_id: str,
    *,
    skeleton_json_sha256: str,
    bundle_sha256: str,
) -> P10Spine42V3CommandResult:
    """Replay one exact historical address without observing current heads."""

    try:
        skeleton_sha = require_sha256(
            skeleton_json_sha256, "Spine v3 skeleton digest"
        )
        bundle_sha = require_sha256(bundle_sha256, "Spine v3 bundle digest")
        verified = VerifiedSpine42V3BundleReader(Path(state_root)).load(
            project_id, skeleton_sha, bundle_sha
        )
        if verified.project_id != project_id \
                or verified.skeleton_json_sha256 != skeleton_sha \
                or verified.bundle_sha256 != bundle_sha:
            raise ValueError("Spine v3 historical address differs")
        return _result(
            "verified", verified, None,
            head_check={
                "scope": "historical_replay",
                "current_heads_observed": False,
                "permanent_authority_claimed": False,
            },
        )
    except _COMMAND_FAILURES as exc:
        raise P10Spine42V3CommandError(
            "Body-sway Spine 4.2 v3 verification failed"
        ) from exc


def _require_motion_source(compilation, motion) -> None:
    if type(compilation) is not VerifiedSpine42V3Compilation \
            or compilation.project_id != motion.project_id \
            or compilation.clip_id != motion.clip_id \
            or compilation.motion_instance_v3_sha256 \
                != motion.motion_instance_v3_sha256 \
            or compilation.motion_instance_v3_bundle_sha256 \
                != motion.bundle_sha256:
        raise ValueError("Spine v3 compilation source differs")


def _require_published(published, expected) -> None:
    if type(published) is not PublishedSpine42V3Bundle \
            or published.project_id != expected.project_id \
            or published.clip_id != expected.clip_id \
            or published.skeleton_json_sha256 \
                != expected.skeleton_json_sha256 \
            or published.bundle_sha256 != expected.bundle_sha256 \
            or published.run_document_sha256 \
                != expected.run_document_sha256 \
            or type(published.reused) is not bool:
        raise ValueError("Spine v3 store postcondition failed")
    suffix = (
        published.path.name, published.path.parent.name,
        published.path.parent.parent.name,
        published.path.parent.parent.parent.name,
        published.path.parent.parent.parent.parent.name,
    )
    if suffix != (
        expected.bundle_sha256, expected.skeleton_json_sha256,
        NAMESPACE, expected.project_id, "builds",
    ):
        raise ValueError("Spine v3 store path postcondition failed")


def _require_exact_readback(verified, expected) -> None:
    if type(verified) is not VerifiedSpine42V3Bundle \
            or verified.project_id != expected.project_id \
            or verified.clip_id != expected.clip_id \
            or verified.contract_identities != expected.contract_identities \
            or verified.source_image_sha256s != expected.source_image_sha256s \
            or verified.document_bytes != expected.document_bytes:
        raise ValueError("Published Spine v3 exact readback failed")


def _result(mode, verified, reused, *, head_check):
    run = verified.run_manifest
    document = {
        "project_id": verified.project_id,
        "clip_id": verified.clip_id,
        "source": {
            "p3": verified.p3_source,
            "motion_instance_v3": verified.motion_instance_v3_source,
        },
        "address": {
            "skeleton_json_sha256": verified.skeleton_json_sha256,
            "bundle_sha256": verified.bundle_sha256,
        },
        "outputs": {
            name: getattr(verified, name) for name in (
                "atlas_sha256", "png_sha256", "run_identity_sha256",
                "run_document_sha256", "report_sha256",
            )
        },
        "inventory": list(verified.inventory),
        "authority": run["authority"],
        "release_gate": run["release_gate"],
        "reused": reused,
        "head_check": head_check,
        "verification": {
            "status": "passed",
            "exact_historical_replay": True,
        },
    }
    return P10Spine42V3CommandResult(
        mode, verified.project_id, verified.clip_id,
        verified.skeleton_json_sha256, verified.bundle_sha256, reused,
        canonical_json_bytes(document).decode("utf-8"),
    )


_COMMAND_FAILURES = (
    AttributeError, KeyError, OSError, OverflowError, RecursionError,
    RuntimeError, TypeError, UnicodeError, ValueError,
)


__all__ = [
    "P10Spine42V3CommandError", "P10Spine42V3CommandResult",
    "compile_body_sway_spine42_v3_command",
    "verify_body_sway_spine42_v3_command",
]
