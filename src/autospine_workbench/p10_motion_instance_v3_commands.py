"""Application commands for compiling and verifying P10.6b bundles."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
from typing import Any

from .body_sway_dynamic_seam_head_checks import (
    require_current_body_sway_dynamic_seam_heads,
)
from .body_sway_motion_consumer_validation import (
    body_sway_motion_consumer_admission_canonical_bytes,
)
from .manifest_artifacts import require_sha256
from .motion_instance_v3_bundle_contract import (
    MotionInstanceV3BundleContract,
    build_motion_instance_v3_bundle_contract,
)
from .motion_instance_v3_bundle_files import NAMESPACE
from .motion_instance_v3_bundle_integrity import (
    VerifiedMotionInstanceV3Bundle,
)
from .motion_instance_v3_bundle_reader import (
    VerifiedMotionInstanceV3BundleReader,
)
from .motion_instance_v3_bundle_store import (
    MotionInstanceV3BundleStore,
    PublishedMotionInstanceV3Bundle,
)
from .motion_instance_v3_compiler import compile_motion_instance_v3
from .p10_motion_instance_v3_command_input import read_admission_wrapper
from .reviewed_motion_bundle_reader import VerifiedReviewedMotionBundleReader
from .seam_anchor_review_json import canonical_json_bytes


class P10MotionInstanceV3CommandError(RuntimeError):
    """Raised with one fixed, path-free P10.6b failure message."""


@dataclass(frozen=True, slots=True)
class P10MotionInstanceV3CommandResult:
    """Frozen path-free command output with copy-isolated JSON access."""

    mode: str
    project_id: str
    clip_id: str
    motion_instance_v3_sha256: str
    bundle_sha256: str
    run_sha256: str
    reused: bool | None
    _canonical_json: str = field(repr=False)

    @property
    def document(self) -> dict[str, Any]:
        return json.loads(self._canonical_json)


def compile_body_sway_motion_instance_v3_command(
    state_root: Path,
    project_id: str,
    admission_wrapper_path: Path,
    *,
    admission_sha256: str,
) -> P10MotionInstanceV3CommandResult:
    """Compile between two head observations, then publish exactly once."""

    try:
        wrapper = read_admission_wrapper(
            admission_wrapper_path, project_id, admission_sha256
        )
        admission = wrapper["admission"]
        p9 = admission["source"]["p9"]
        reviewed = VerifiedReviewedMotionBundleReader(Path(state_root)).load(
            project_id,
            p9["motion_instance_v2_sha256"],
            p9["bundle_sha256"],
        )
        admission_bytes = body_sway_motion_consumer_admission_canonical_bytes(
            admission, reviewed_bundle=reviewed
        )
        expected_admission_sha = require_sha256(
            admission_sha256, "Body-sway motion-consumer admission digest"
        )
        if hashlib.sha256(admission_bytes).hexdigest() \
                != expected_admission_sha:
            raise ValueError("admission address mismatch")
        source = admission["source"][
            "body_sway_dynamic_seam_probe"
        ]["source"]
        before = require_current_body_sway_dynamic_seam_heads(
            Path(state_root), source
        )
        compiled = compile_motion_instance_v3(admission, reviewed)
        pending = build_motion_instance_v3_bundle_contract(
            project_id, admission, compiled.document, reviewed
        )
        after = require_current_body_sway_dynamic_seam_heads(
            Path(state_root), source
        )
        _require_unchanged_heads(before, after)
        published = MotionInstanceV3BundleStore(Path(state_root)).publish(
            project_id, admission, compiled.document, reviewed
        )
        _require_published(published, pending)
        verified = VerifiedMotionInstanceV3BundleReader(
            Path(state_root)
        ).load(
            project_id,
            published.motion_instance_v3_sha256,
            published.bundle_sha256,
        )
        _require_verified_contract(verified, pending)
        return _result(
            "compiled", verified.identities, verified.project_id,
            verified.clip_id, verified.inventory, published.reused,
            head_check={
                "scope": "prepublication_compile",
                "before_after_identity": "exact_match",
                "before_after_canonical_bytes": "exact_match",
                "current_heads_observed": True,
                "permanent_authority_claimed": False,
            },
        )
    except _COMMAND_FAILURES as exc:
        raise P10MotionInstanceV3CommandError(
            "Body-sway MotionInstance v3 compilation failed"
        ) from exc


def verify_body_sway_motion_instance_v3_command(
    state_root: Path,
    project_id: str,
    *,
    motion_instance_v3_sha256: str,
    bundle_sha256: str,
) -> P10MotionInstanceV3CommandResult:
    """Replay one exact historical address without observing current heads."""

    try:
        expected_v3 = require_sha256(
            motion_instance_v3_sha256, "MotionInstance v3 digest"
        )
        expected_bundle = require_sha256(
            bundle_sha256, "MotionInstance v3 bundle digest"
        )
        verified = VerifiedMotionInstanceV3BundleReader(
            Path(state_root)
        ).load(project_id, expected_v3, expected_bundle)
        _require_verified_address(
            verified, project_id, expected_v3, expected_bundle
        )
        return _result(
            "verified", verified.identities, verified.project_id,
            verified.clip_id, verified.inventory, None,
            head_check={
                "scope": "historical_replay",
                "current_heads_observed": False,
                "permanent_authority_claimed": False,
            },
        )
    except _COMMAND_FAILURES as exc:
        raise P10MotionInstanceV3CommandError(
            "Body-sway MotionInstance v3 verification failed"
        ) from exc


def _require_unchanged_heads(before, after) -> None:
    if before.identity != after.identity \
            or before.canonical_bytes != after.canonical_bytes:
        raise ValueError("current review heads drifted before publication")


def _require_published(published, expected) -> None:
    if type(published) is not PublishedMotionInstanceV3Bundle \
            or published.project_id != expected.project_id \
            or published.clip_id != expected.clip_id \
            or published.motion_instance_v3_sha256 \
            != expected.motion_instance_v3_sha256 \
            or published.bundle_sha256 != expected.bundle_sha256 \
            or published.run_sha256 != expected.run_sha256 \
            or type(published.reused) is not bool:
        raise ValueError("MotionInstance v3 store postcondition failed")
    suffix = (
        published.path.name, published.path.parent.name,
        published.path.parent.parent.name,
        published.path.parent.parent.parent.name,
        published.path.parent.parent.parent.parent.name,
    )
    if suffix != (
        expected.bundle_sha256, expected.motion_instance_v3_sha256,
        NAMESPACE, expected.project_id, "builds",
    ):
        raise ValueError("MotionInstance v3 store path postcondition failed")


def _require_verified_address(
    verified, project_id, expected_v3, expected_bundle
) -> None:
    if type(verified) is not VerifiedMotionInstanceV3Bundle \
            or verified.project_id != project_id \
            or verified.motion_instance_v3_sha256 != expected_v3 \
            or verified.bundle_sha256 != expected_bundle:
        raise ValueError("MotionInstance v3 verification postcondition failed")


def _require_verified_contract(
    verified: VerifiedMotionInstanceV3Bundle,
    expected: MotionInstanceV3BundleContract,
) -> None:
    if (
        type(verified) is not VerifiedMotionInstanceV3Bundle
        or verified.project_id != expected.project_id
        or verified.clip_id != expected.clip_id
        or verified.inventory != expected.inventory
        or verified.identities != expected.identities
        or verified.document_bytes != expected.document_bytes
    ):
        raise ValueError(
            "Published MotionInstance v3 exact readback failed"
        )


def _result(mode, identities, project_id, clip_id, inventory, reused,
            *, head_check):
    document = {
        "project_id": project_id,
        "clip_id": clip_id,
        "source": {
            field: identities[field] for field in (
                "admission_sha256", "motion_instance_v2_sha256",
                "reviewed_motion_bundle_sha256", "motion_domain_sha256",
                "rotation_timeline_sha256", "base_channels_sha256",
                "rig_ir_sha256", "target_profile_sha256",
                "motion_instance_v3_profile_sha256",
            )
        },
        "address": {
            "motion_instance_v3_sha256": identities[
                "motion_instance_v3_sha256"
            ],
            "bundle_sha256": identities["bundle_sha256"],
        },
        "run_sha256": identities["run_sha256"],
        "inventory": list(inventory),
        "reused": reused,
        "head_check": head_check,
        "verification": {
            "status": "passed",
            "exact_historical_replay": True,
        },
    }
    return P10MotionInstanceV3CommandResult(
        mode, project_id, clip_id, identities["motion_instance_v3_sha256"],
        identities["bundle_sha256"], identities["run_sha256"], reused,
        canonical_json_bytes(document).decode("utf-8"),
    )


_COMMAND_FAILURES = (
    AttributeError, KeyError, OSError, OverflowError, RecursionError,
    RuntimeError, TypeError, UnicodeError, ValueError,
)
