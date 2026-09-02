"""Path-free replayable P10.7b v2 runtime-source admission."""

from __future__ import annotations

from collections.abc import Mapping
import json
from typing import Any

from .resolved_project import canonical_sha256
from .spine42_v3_bundle_reader_v2 import VerifiedSpine42V3BundleV2
from .spine42_v3_runtime_plan_v2 import (
    require_spine42_v3_runtime_plan_v2,
)
from .spine42_v3_runtime_profile_v2 import (
    ADMISSION_HASH_DOMAIN,
    spine42_v3_runtime_profile_sha256_v2,
    spine42_v3_runtime_source_contract_sha256_v2,
    spine42_v3_runtime_source_contract_v2,
)


ADMISSION_FORMAT = "autospine-spine42-v3-runtime-source-admission"
ADMISSION_VERSION = 2

_AUTHORITY = {
    "p10_7a_v2_exact_replayed": True,
    "bounded_capture_plan_emitted": True,
    "official_runtime_loaded": False,
    "runtime_equivalence": False,
    "raster_metrics_computed": False,
    "raster_visual_quality": False,
    "human_visual_reviewed": False,
    "persistent_current_head_authority": False,
    "publishable_spine_timeline": False,
    "release_authority": False,
}
_REASON_CODES = (
    "official_runtime_not_loaded",
    "runtime_equivalence_not_assessed",
    "raster_metrics_not_computed",
    "raster_visual_quality_not_reviewed",
    "human_visual_review_not_completed",
    "persistent_current_head_authority_not_granted",
    "publishable_spine_timeline_not_proven",
    "release_authority_not_granted",
)


class Spine42V3RuntimeSourceAdmissionV2Error(ValueError):
    """Raised when a v2 source admission cannot be replayed exactly."""


def build_spine42_v3_runtime_source_admission_v2(
    bundle: VerifiedSpine42V3BundleV2,
    plan: Mapping[str, Any],
) -> dict[str, Any]:
    """Admit exact v2 bytes for planning, never for runtime/raster/release."""

    try:
        if type(bundle) is not VerifiedSpine42V3BundleV2:
            raise Spine42V3RuntimeSourceAdmissionV2Error(
                "Runtime source admission v2 requires a P10.7a v2 bundle"
            )
        exact_plan = require_spine42_v3_runtime_plan_v2(
            plan, bundle=bundle,
        )
        contract = spine42_v3_runtime_source_contract_v2()
        body = {
            "format": ADMISSION_FORMAT,
            "format_version": ADMISSION_VERSION,
            "project_id": bundle.project_id,
            "clip_id": bundle.clip_id,
            "source_contract_sha256": (
                spine42_v3_runtime_source_contract_sha256_v2()
            ),
            "source_contract": contract,
            "profile_sha256": spine42_v3_runtime_profile_sha256_v2(),
            "source": exact_plan["source"],
            "capture_plan_sha256": exact_plan["capture_plan_sha256"],
            "authority": dict(_AUTHORITY),
            "release_gate": {
                "status": "blocked",
                "reason_codes": list(_REASON_CODES),
            },
        }
        return {
            **body,
            "admission_sha256": canonical_sha256({
                "domain": ADMISSION_HASH_DOMAIN, **body,
            }),
        }
    except Spine42V3RuntimeSourceAdmissionV2Error:
        raise
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise Spine42V3RuntimeSourceAdmissionV2Error(
            f"Runtime source admission v2 failed: {exc}"
        ) from exc


def require_spine42_v3_runtime_source_admission_v2(
    value: Mapping[str, Any],
    *,
    bundle: VerifiedSpine42V3BundleV2,
    plan: Mapping[str, Any],
) -> dict[str, Any]:
    """Require canonical equality with detached exact recomputation."""

    canonical = canonical_spine42_v3_runtime_source_admission_bytes_v2(value)
    spine42_v3_runtime_source_admission_sha256_v2(value)
    expected = build_spine42_v3_runtime_source_admission_v2(bundle, plan)
    if canonical != canonical_spine42_v3_runtime_source_admission_bytes_v2(
        expected
    ):
        raise Spine42V3RuntimeSourceAdmissionV2Error(
            "Runtime source admission v2 differs from exact replay"
        )
    return json.loads(canonical)


def spine42_v3_runtime_source_admission_sha256_v2(
    value: Mapping[str, Any],
) -> str:
    try:
        body = json.loads(
            canonical_spine42_v3_runtime_source_admission_bytes_v2(value)
        )
        supplied = body.pop("admission_sha256", None)
        if body.get("format") != ADMISSION_FORMAT \
                or body.get("format_version") != ADMISSION_VERSION:
            raise Spine42V3RuntimeSourceAdmissionV2Error(
                "Runtime source admission v2 format is unsupported"
            )
        result = canonical_sha256({"domain": ADMISSION_HASH_DOMAIN, **body})
        if supplied != result:
            raise Spine42V3RuntimeSourceAdmissionV2Error(
                "Runtime source admission v2 digest is inconsistent"
            )
        return result
    except Spine42V3RuntimeSourceAdmissionV2Error:
        raise
    except (AttributeError, TypeError, ValueError) as exc:
        raise Spine42V3RuntimeSourceAdmissionV2Error(
            "Runtime source admission v2 cannot be hashed"
        ) from exc


def canonical_spine42_v3_runtime_source_admission_bytes_v2(
    value: Mapping[str, Any],
) -> bytes:
    if not isinstance(value, Mapping):
        raise Spine42V3RuntimeSourceAdmissionV2Error(
            "Runtime source admission v2 must be an object"
        )
    try:
        return json.dumps(
            dict(value), ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
    except (OverflowError, TypeError, UnicodeError, ValueError) as exc:
        raise Spine42V3RuntimeSourceAdmissionV2Error(
            "Runtime source admission v2 is not strict finite JSON"
        ) from exc


__all__ = [
    "ADMISSION_FORMAT", "ADMISSION_VERSION",
    "Spine42V3RuntimeSourceAdmissionV2Error",
    "build_spine42_v3_runtime_source_admission_v2",
    "canonical_spine42_v3_runtime_source_admission_bytes_v2",
    "require_spine42_v3_runtime_source_admission_v2",
    "spine42_v3_runtime_source_admission_sha256_v2",
]
