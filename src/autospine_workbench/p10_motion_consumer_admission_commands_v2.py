"""Zero-write exact-bundle orchestration for P10.6a v2."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import hashlib
import json
from typing import Any

from .body_sway_dynamic_seam_bundle_reader_v2 import (
    BodySwayDynamicSeamBundleReaderV2,
    BodySwayDynamicSeamBundleReaderV2Error,
)
from .body_sway_dynamic_seam_head_checks_v2 import (
    BodySwayDynamicSeamHeadCheckV2Error,
    require_current_body_sway_dynamic_seam_heads_v2,
)
from .body_sway_motion_consumer_admission_v2 import (
    BodySwayMotionConsumerAdmissionV2Error,
    seal_body_sway_motion_consumer_admission_v2,
)
from .body_sway_motion_consumer_core_v2 import (
    compile_body_sway_motion_consumer_admission_core_v2,
)
from .body_sway_motion_consumer_validation_v2 import (
    BodySwayMotionConsumerAdmissionV2ValidationError,
    body_sway_motion_consumer_admission_canonical_bytes_v2,
)
from .manifest_artifacts import require_sha256
from .project_store import ProjectStore, ProjectStoreError
from .reviewed_motion_bundle_reader import (
    VerifiedReviewedMotionBundleReader,
    VerifiedReviewedMotionBundleReaderError,
)
from .seam_anchor_review_json import canonical_json_bytes


class P10MotionConsumerAdmissionCommandV2Error(RuntimeError):
    """Raised when one exact read-only P10.6a v2 command fails closed."""


@dataclass(frozen=True, slots=True)
class P10MotionConsumerAdmissionCommandResultV2:
    """Path-free P10.6a v2 result with copy-isolated JSON access."""

    project_id: str
    clip_id: str
    dynamic_seam_probe_sha256: str
    dynamic_seam_bundle_sha256: str
    motion_instance_v2_sha256: str
    reviewed_motion_bundle_sha256: str
    admission_sha256: str
    _canonical_json: str = field(repr=False)

    @property
    def document(self) -> dict[str, Any]:
        return json.loads(self._canonical_json)


def compile_body_sway_motion_consumer_admission_v2_command(
    capture_job_reader,
    project_store: ProjectStore,
    project_id: str,
    *,
    dynamic_seam_probe_sha256: str,
    dynamic_seam_bundle_sha256: str,
) -> P10MotionConsumerAdmissionCommandResultV2:
    """Read P10.5d/P9 exactly and seal between two current-head reads."""

    try:
        _require_stores(capture_job_reader, project_store)
        probe_sha = require_sha256(
            dynamic_seam_probe_sha256, "P10.5d v2 probe digest",
        )
        bundle_sha = require_sha256(
            dynamic_seam_bundle_sha256, "P10.5d v2 bundle digest",
        )
        dynamic = BodySwayDynamicSeamBundleReaderV2(
            project_store.state_root
        ).load(project_id, probe_sha, bundle_sha)
        p9 = _p9_address(dynamic.source)
        reviewed = VerifiedReviewedMotionBundleReader(
            project_store.state_root
        ).load(
            project_id, p9["motion_instance_v2_sha256"],
            p9["bundle_sha256"],
        )
        _require_exact_inputs(
            dynamic, reviewed, project_id, p9, probe_sha, bundle_sha,
        )
        before = require_current_body_sway_dynamic_seam_heads_v2(
            capture_job_reader, project_store, dynamic.source,
        )
        core = compile_body_sway_motion_consumer_admission_core_v2(
            dynamic, reviewed,
        )
        after = require_current_body_sway_dynamic_seam_heads_v2(
            capture_job_reader, project_store, dynamic.source,
        )
        _require_same_heads(before, after)
        admission = seal_body_sway_motion_consumer_admission_v2(
            core, before, after,
        )
        replayed = body_sway_motion_consumer_admission_canonical_bytes_v2(
            admission.document,
            dynamic_seam_bundle=dynamic,
            reviewed_bundle=reviewed,
        )
        admission_sha = hashlib.sha256(replayed).hexdigest()
        if replayed != admission.canonical_bytes \
                or admission.sha256 != admission_sha:
            raise P10MotionConsumerAdmissionCommandV2Error(
                "P10.6a v2 admission differs from detached replay"
            )
        document = _result_document(
            admission.document, dynamic, p9, admission_sha, before, after,
        )
        return P10MotionConsumerAdmissionCommandResultV2(
            dynamic.project_id, dynamic.clip_id,
            dynamic.probe_sha256, dynamic.bundle_sha256,
            p9["motion_instance_v2_sha256"], p9["bundle_sha256"],
            admission_sha, _canonical(document),
        )
    except P10MotionConsumerAdmissionCommandV2Error:
        raise
    except _FAILURES as exc:
        raise P10MotionConsumerAdmissionCommandV2Error(
            "Body-sway motion-consumer admission v2 compilation failed"
        ) from exc


def _require_stores(capture_job_reader, project_store):
    if type(project_store) is not ProjectStore \
            or not callable(getattr(capture_job_reader, "get", None)):
        raise P10MotionConsumerAdmissionCommandV2Error(
            "P10.6a v2 requires exact read-only stores"
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


def _require_exact_inputs(
    dynamic, reviewed, project_id, p9, probe_sha, bundle_sha,
):
    if dynamic.project_id != project_id \
            or dynamic.probe_sha256 != probe_sha \
            or dynamic.bundle_sha256 != bundle_sha \
            or reviewed.project_id != project_id \
            or reviewed.clip_id != dynamic.clip_id \
            or reviewed.motion_instance_v2_sha256 \
                != p9["motion_instance_v2_sha256"] \
            or reviewed.bundle_sha256 != p9["bundle_sha256"]:
        raise P10MotionConsumerAdmissionCommandV2Error(
            "P10.5d v2 or P9 bundle differs from its exact address"
        )


def _require_same_heads(before, after):
    if before.identity_sha256 != after.identity_sha256 \
            or before.canonical_bytes != after.canonical_bytes:
        raise P10MotionConsumerAdmissionCommandV2Error(
            "P10.6a v2 current review heads changed during compilation"
        )


def _result_document(admission, dynamic, p9, admission_sha, before, after):
    return {
        "project_id": dynamic.project_id,
        "clip_id": dynamic.clip_id,
        "dynamic_seam_address": {
            "probe_sha256": dynamic.probe_sha256,
            "bundle_sha256": dynamic.bundle_sha256,
        },
        "reviewed_motion_address": {
            "motion_instance_v2_sha256": p9["motion_instance_v2_sha256"],
            "reviewed_motion_bundle_sha256": p9["bundle_sha256"],
        },
        "body_sway_motion_consumer_admission_v2_sha256": admission_sha,
        "admission": admission,
        "head_observation": {
            "method": "outer-before-after-consumer-v2-core-compilation",
            "scope": "compile_time",
            "before": before.document,
            "after": after.document,
            "checks": {
                "before_after_identity": "exact_match",
                "before_after_documents": "canonical_bytes_exact_match",
            },
            "permanent_authority_claimed": False,
        },
    }


def _canonical(value):
    return canonical_json_bytes(value).decode("utf-8")


_FAILURES = (
    AttributeError, BodySwayDynamicSeamBundleReaderV2Error,
    BodySwayDynamicSeamHeadCheckV2Error,
    BodySwayMotionConsumerAdmissionV2Error,
    BodySwayMotionConsumerAdmissionV2ValidationError, KeyError, OSError,
    OverflowError, ProjectStoreError, RecursionError, RuntimeError,
    TypeError, UnicodeError, ValueError,
    VerifiedReviewedMotionBundleReaderError,
)


__all__ = [
    "P10MotionConsumerAdmissionCommandResultV2",
    "P10MotionConsumerAdmissionCommandV2Error",
    "compile_body_sway_motion_consumer_admission_v2_command",
]
