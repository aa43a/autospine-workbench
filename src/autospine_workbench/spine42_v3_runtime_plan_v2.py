"""Pure version-isolated P10.7b v2 bounded capture plan."""

from __future__ import annotations

from collections.abc import Mapping
import json
from typing import Any

from .manifest_artifacts import LayerManifestError, require_safe_token, require_sha256
from .resolved_project import canonical_sha256
from .spine42_v3_bundle_reader_v2 import VerifiedSpine42V3BundleV2
from .spine42_v3_runtime_plan_semantics import (
    derive_runtime_capture_plan_semantics,
)
from .spine42_v3_runtime_profile_v2 import (
    MAX_CAPTURE_ARTIFACTS,
    MAX_COMPOSITE_CASES,
    MAX_SETUP_ATTACHMENTS,
    P10_7A_V2_IDENTITY_FIELDS,
    PLAN_HASH_DOMAIN,
    TICKS_PER_SECOND,
    spine42_v3_runtime_profile_sha256_v2,
    spine42_v3_runtime_profile_v2,
    spine42_v3_runtime_source_contract_sha256_v2,
)


PLAN_FORMAT = "autospine-spine42-v3-runtime-raster-plan"
PLAN_VERSION = 2
SOURCE_FORMAT = "autospine-spine42-v3-runtime-source"
SOURCE_VERSION = 2


class Spine42V3RuntimePlanV2Error(ValueError):
    """Raised when an exact v2 adapter bundle cannot form a v2 plan."""


def build_spine42_v3_runtime_plan_v2(
    bundle: VerifiedSpine42V3BundleV2,
) -> dict[str, Any]:
    """Bind the shared capture cases to one reader-issued P10.7a v2 source."""

    try:
        if type(bundle) is not VerifiedSpine42V3BundleV2:
            raise Spine42V3RuntimePlanV2Error(
                "Runtime planning v2 requires a reader-issued P10.7a v2 bundle"
            )
        project = require_safe_token(bundle.project_id, "Project id")
        clip = require_safe_token(bundle.clip_id, "Clip id")
        identities = _identities(bundle.contract_identities)
        semantics = derive_runtime_capture_plan_semantics(
            bundle.skeleton_json, clip, ticks_per_second=TICKS_PER_SECOND,
            max_composite_cases=MAX_COMPOSITE_CASES,
            max_setup_attachments=MAX_SETUP_ATTACHMENTS,
            max_capture_artifacts=MAX_CAPTURE_ARTIFACTS,
        )
        profile = spine42_v3_runtime_profile_v2()
        body = {
            "format": PLAN_FORMAT,
            "format_version": PLAN_VERSION,
            "source_contract_sha256": (
                spine42_v3_runtime_source_contract_sha256_v2()
            ),
            "profile_sha256": spine42_v3_runtime_profile_sha256_v2(),
            "source": {
                "format": SOURCE_FORMAT,
                "format_version": SOURCE_VERSION,
                "project_id": project,
                "clip_id": clip,
                "spine42_v3_v2": identities,
            },
            "runtime": profile["runtime"],
            "harness": profile["harness"],
            "browser_execution": profile["browser_execution"],
            "capture": {
                **profile["capture"],
                "world_viewport": semantics["world_viewport"],
            },
            "sampled_scope": semantics["sampled_scope"],
            "attachments": semantics["attachments"],
            "cases": semantics["cases"],
            "artifacts": semantics["artifacts"],
        }
        return {
            **body,
            "capture_plan_sha256": canonical_sha256({
                "domain": PLAN_HASH_DOMAIN, **body,
            }),
        }
    except Spine42V3RuntimePlanV2Error:
        raise
    except (
        AttributeError, KeyError, LayerManifestError, OverflowError,
        TypeError, UnicodeError, ValueError,
    ) as exc:
        raise Spine42V3RuntimePlanV2Error(
            f"Spine v3 runtime capture planning v2 failed: {exc}"
        ) from exc


def require_spine42_v3_runtime_plan_v2(
    value: Mapping[str, Any],
    *,
    bundle: VerifiedSpine42V3BundleV2,
) -> dict[str, Any]:
    """Require byte-exact recomputation from the same reader-issued bundle."""

    canonical = canonical_spine42_v3_runtime_plan_bytes_v2(value)
    spine42_v3_runtime_plan_sha256_v2(value)
    expected = build_spine42_v3_runtime_plan_v2(bundle)
    if canonical != canonical_spine42_v3_runtime_plan_bytes_v2(expected):
        raise Spine42V3RuntimePlanV2Error(
            "Runtime capture plan v2 differs from exact source replay"
        )
    return json.loads(canonical)


def spine42_v3_runtime_plan_sha256_v2(plan: Mapping[str, Any]) -> str:
    """Return the v2-domain identity after checking its self-hash."""

    try:
        body = json.loads(canonical_spine42_v3_runtime_plan_bytes_v2(plan))
        supplied = body.pop("capture_plan_sha256", None)
        if body.get("format") != PLAN_FORMAT \
                or body.get("format_version") != PLAN_VERSION:
            raise Spine42V3RuntimePlanV2Error(
                "Runtime capture plan v2 format is unsupported"
            )
        result = canonical_sha256({"domain": PLAN_HASH_DOMAIN, **body})
        if supplied != result:
            raise Spine42V3RuntimePlanV2Error(
                "Runtime capture plan v2 digest is inconsistent"
            )
        return result
    except Spine42V3RuntimePlanV2Error:
        raise
    except (AttributeError, TypeError, ValueError) as exc:
        raise Spine42V3RuntimePlanV2Error(
            "Runtime capture plan v2 cannot be hashed"
        ) from exc


def canonical_spine42_v3_runtime_plan_bytes_v2(
    value: Mapping[str, Any],
) -> bytes:
    if not isinstance(value, Mapping):
        raise Spine42V3RuntimePlanV2Error(
            "Runtime capture plan v2 must be an object"
        )
    try:
        return json.dumps(
            dict(value), ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
    except (OverflowError, TypeError, UnicodeError, ValueError) as exc:
        raise Spine42V3RuntimePlanV2Error(
            "Runtime capture plan v2 is not strict finite JSON"
        ) from exc


def _identities(value: Any) -> dict[str, str]:
    if type(value) is not dict or set(value) != set(P10_7A_V2_IDENTITY_FIELDS):
        raise Spine42V3RuntimePlanV2Error(
            "P10.7a v2 source identity inventory is invalid"
        )
    return {
        name: require_sha256(value[name], f"P10.7a v2 {name}")
        for name in P10_7A_V2_IDENTITY_FIELDS
    }


__all__ = [
    "PLAN_FORMAT", "PLAN_VERSION", "SOURCE_FORMAT", "SOURCE_VERSION",
    "Spine42V3RuntimePlanV2Error", "build_spine42_v3_runtime_plan_v2",
    "canonical_spine42_v3_runtime_plan_bytes_v2",
    "require_spine42_v3_runtime_plan_v2",
    "spine42_v3_runtime_plan_sha256_v2",
]
