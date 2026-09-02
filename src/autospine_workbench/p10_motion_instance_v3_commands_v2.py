"""One-pass exact-address orchestration for P10.6b v2."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
from typing import Any

from .body_sway_dynamic_seam_bundle_reader_v2 import (
    BodySwayDynamicSeamBundleReaderV2,
    BodySwayDynamicSeamBundleReaderV2Error,
)
from .body_sway_dynamic_seam_head_checks_v2 import (
    BodySwayDynamicSeamHeadCheckV2Error,
    require_current_body_sway_dynamic_seam_heads_v2,
)
from .manifest_artifacts import require_sha256
from .motion_instance_v3_bundle_reader_v2 import (
    MotionInstanceV3BundleReaderV2,
    MotionInstanceV3BundleReaderV2Error,
    VerifiedMotionInstanceV3BundleV2,
)
from .motion_instance_v3_bundle_store_v2 import (
    MotionInstanceV3BundleStoreV2,
    MotionInstanceV3BundleStoreV2Error,
    PublishedMotionInstanceV3BundleV2,
)
from .motion_instance_v3_compiler_v2 import (
    MotionInstanceV3V2CompilerError,
    compile_motion_instance_v3_v2,
)
from .motion_instance_v3_prepared_v2 import (
    MotionInstanceV3PreparedV2Error,
    compile_motion_instance_v3_prepared_core_v2,
    seal_motion_instance_v3_prepared_v2,
)
from .project_store import ProjectStore, ProjectStoreError
from .reviewed_motion_bundle_reader import (
    VerifiedReviewedMotionBundleReader,
    VerifiedReviewedMotionBundleReaderError,
)
from .seam_anchor_review_json import canonical_json_bytes


class P10MotionInstanceV3CommandV2Error(RuntimeError):
    """Raised with one fixed, path-free P10.6b v2 failure message."""
@dataclass(frozen=True, slots=True)
class P10MotionInstanceV3CommandResultV2:
    """Copy-isolated path-free compile or historical verify output."""

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
def compile_body_sway_motion_instance_v3_v2_command(
    capture_job_reader,
    project_store: ProjectStore,
    project_id: str,
    *,
    dynamic_seam_probe_sha256: str,
    dynamic_seam_bundle_sha256: str,
) -> P10MotionInstanceV3CommandResultV2:
    """Read P10.5d once, prepare v2 admission, publish, and read back."""

    try:
        _require_stores(capture_job_reader, project_store)
        probe_sha = require_sha256(
            dynamic_seam_probe_sha256, "P10.5d v2 probe digest",
        )
        bundle_sha = require_sha256(
            dynamic_seam_bundle_sha256, "P10.5d v2 bundle digest",
        )
        dynamic = BodySwayDynamicSeamBundleReaderV2(
            project_store.state_root,
        ).load(project_id, probe_sha, bundle_sha)
        p9 = _p9_address(dynamic.source)
        reviewed = VerifiedReviewedMotionBundleReader(
            project_store.state_root,
        ).load(
            project_id, p9["motion_instance_v2_sha256"],
            p9["bundle_sha256"],
        )
        before = require_current_body_sway_dynamic_seam_heads_v2(
            capture_job_reader, project_store, dynamic.source,
        )
        core = compile_motion_instance_v3_prepared_core_v2(
            dynamic, reviewed,
        )
        after = require_current_body_sway_dynamic_seam_heads_v2(
            capture_job_reader, project_store, dynamic.source,
        )
        _require_same_heads(before, after)
        prepared = seal_motion_instance_v3_prepared_v2(
            core, before, after,
        )
        _require_admission_identity(prepared)
        motion = compile_motion_instance_v3_v2(prepared)
        published = MotionInstanceV3BundleStoreV2(
            capture_job_reader, project_store,
        ).publish(prepared, motion.document, dynamic, reviewed)
        verified = MotionInstanceV3BundleReaderV2(
            project_store.state_root,
        ).load(
            project_id, published.motion_instance_v3_sha256,
            published.bundle_sha256, dynamic_bundle=dynamic,
            reviewed_bundle=reviewed, prepared=prepared,
        )
        _require_compile_postconditions(
            published, verified, prepared, motion.sha256,
        )
        return _result(
            "compiled", verified, published.reused,
            head_check={
                "scope": "compile_time_and_prepublication",
                "current_heads_observed": True,
                "before_after_identity": "exact_match",
                "before_after_canonical_bytes": "exact_match",
                "permanent_authority_claimed": False,
            },
        )
    except P10MotionInstanceV3CommandV2Error:
        raise
    except _FAILURES as exc:
        raise P10MotionInstanceV3CommandV2Error(
            "Body-sway MotionInstance v3 v2 compilation failed"
        ) from exc


def verify_body_sway_motion_instance_v3_v2_command(
    state_root: Path,
    project_id: str,
    *,
    motion_instance_v3_sha256: str,
    bundle_sha256: str,
) -> P10MotionInstanceV3CommandResultV2:
    """Replay one exact historical v2-source bundle without current heads."""

    try:
        primary = require_sha256(
            motion_instance_v3_sha256, "MotionInstance v3 digest",
        )
        bundle = require_sha256(
            bundle_sha256, "MotionInstance v3 v2 bundle digest",
        )
        verified = MotionInstanceV3BundleReaderV2(Path(state_root)).load(
            project_id, primary, bundle,
        )
        if verified.project_id != project_id \
                or verified.motion_instance_v3_sha256 != primary \
                or verified.bundle_sha256 != bundle:
            raise P10MotionInstanceV3CommandV2Error(
                "Historical P10.6b v2 address differs from exact readback"
            )
        return _result(
            "verified", verified, None,
            head_check={
                "scope": "historical_replay",
                "current_heads_observed": False,
                "permanent_authority_claimed": False,
            },
        )
    except P10MotionInstanceV3CommandV2Error:
        raise
    except _FAILURES as exc:
        raise P10MotionInstanceV3CommandV2Error(
            "Body-sway MotionInstance v3 v2 verification failed"
        ) from exc


def _require_stores(capture, store) -> None:
    if type(store) is not ProjectStore \
            or not callable(getattr(capture, "get", None)):
        raise P10MotionInstanceV3CommandV2Error(
            "P10.6b v2 requires exact local read-only stores"
        )


def _p9_address(source: Mapping[str, Any]) -> dict[str, str]:
    p9 = source["body_sway_continuous_preview_proof_v2"]["source"] \
        ["amplitude_envelope_candidate_v2"]["source"] \
        ["reviewed_probe_report"]["source"]["p9"]
    return {
        "motion_instance_v2_sha256": require_sha256(
            p9["motion_instance_v2_sha256"], "P9 MotionInstance v2 digest",
        ),
        "bundle_sha256": require_sha256(
            p9["bundle_sha256"], "P9 reviewed-motion bundle digest",
        ),
    }


def _require_same_heads(before, after) -> None:
    if before.identity_sha256 != after.identity_sha256 \
            or before.canonical_bytes != after.canonical_bytes:
        raise P10MotionInstanceV3CommandV2Error(
            "P10.6b v2 current review heads changed during preparation"
        )


def _require_admission_identity(prepared) -> None:
    admission_bytes = prepared.admission_bytes
    if not isinstance(admission_bytes, bytes) \
            or hashlib.sha256(admission_bytes).hexdigest() \
                != prepared.admission_sha256:
        raise P10MotionInstanceV3CommandV2Error(
            "P10.6a v2 admission bytes differ from their issued digest"
        )


def _require_compile_postconditions(published, verified, prepared, v3_sha):
    if type(published) is not PublishedMotionInstanceV3BundleV2 \
            or type(verified) is not VerifiedMotionInstanceV3BundleV2 \
            or published.project_id != prepared.project_id \
            or published.clip_id != prepared.clip_id \
            or published.admission_sha256 != prepared.admission_sha256 \
            or published.motion_instance_v3_sha256 != v3_sha \
            or published.motion_instance_v3_sha256 \
                != verified.motion_instance_v3_sha256 \
            or published.bundle_sha256 != verified.bundle_sha256 \
            or published.run_sha256 != verified.run_sha256 \
            or type(published.reused) is not bool:
        raise P10MotionInstanceV3CommandV2Error(
            "P10.6b v2 publication differs from exact readback"
        )


def _result(mode, verified, reused, *, head_check):
    identities = verified.identities
    document = {
        "project_id": verified.project_id,
        "clip_id": verified.clip_id,
        "source": {
            name: identities[name] for name in (
                "admission_sha256", "source_set_sha256",
                "source_document_sha256", "dynamic_seam_probe_sha256",
                "dynamic_seam_bundle_sha256", "motion_instance_v2_sha256",
                "reviewed_motion_bundle_sha256", "motion_domain_sha256",
                "rotation_timeline_sha256", "base_channels_sha256",
                "rig_ir_sha256", "target_profile_sha256",
                "motion_instance_v3_profile_sha256",
            )
        },
        "address": {
            "motion_instance_v3_sha256":
                identities["motion_instance_v3_sha256"],
            "bundle_sha256": identities["bundle_sha256"],
        },
        "run_sha256": identities["run_sha256"],
        "inventory": list(verified.inventory),
        "reused": reused,
        "head_check": head_check,
        "verification": {
            "status": "passed", "exact_readback": True,
        },
    }
    return P10MotionInstanceV3CommandResultV2(
        mode, verified.project_id, verified.clip_id,
        identities["motion_instance_v3_sha256"],
        identities["bundle_sha256"], identities["run_sha256"], reused,
        canonical_json_bytes(document).decode("utf-8"),
    )


_FAILURES = (
    AttributeError, BodySwayDynamicSeamBundleReaderV2Error,
    BodySwayDynamicSeamHeadCheckV2Error, KeyError,
    MotionInstanceV3BundleReaderV2Error,
    MotionInstanceV3BundleStoreV2Error, MotionInstanceV3PreparedV2Error,
    MotionInstanceV3V2CompilerError, OSError, OverflowError,
    ProjectStoreError, RecursionError, RuntimeError, TypeError,
    UnicodeError, ValueError, VerifiedReviewedMotionBundleReaderError,
)


__all__ = [
    "P10MotionInstanceV3CommandResultV2",
    "P10MotionInstanceV3CommandV2Error",
    "compile_body_sway_motion_instance_v3_v2_command",
    "verify_body_sway_motion_instance_v3_v2_command",
]
