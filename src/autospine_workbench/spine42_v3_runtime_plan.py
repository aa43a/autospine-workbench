"""Pure bounded capture planning from one exact verified Spine v3 bundle."""
from __future__ import annotations

from collections.abc import Mapping
import json
from typing import Any

from .resolved_project import canonical_sha256
from .spine42_v3_bundle_integrity import VerifiedSpine42V3Bundle
from .spine42_v3_bundle_integrity import replay_verified_spine42_v3_bundle
from .spine42_v3_runtime_plan_semantics import (
    derive_runtime_capture_plan_semantics,
)
from .spine42_v3_runtime_profile import (
    MAX_CAPTURE_ARTIFACTS,
    MAX_COMPOSITE_CASES,
    MAX_SETUP_ATTACHMENTS,
    PLAN_HASH_DOMAIN,
    TICKS_PER_SECOND,
    spine42_v3_runtime_profile,
    spine42_v3_runtime_profile_sha256,
)


PLAN_FORMAT = "autospine-spine42-v3-runtime-raster-plan"
PLAN_VERSION = 1
class Spine42V3RuntimePlanError(ValueError):
    """Raised when an exact bundle cannot form the bounded capture plan."""


def build_spine42_v3_runtime_plan(
    bundle: VerifiedSpine42V3Bundle,
) -> dict[str, Any]:
    """Derive setup, fixed, extrema, boundary, and loop-neighbor stills."""

    try:
        if type(bundle) is not VerifiedSpine42V3Bundle:
            raise Spine42V3RuntimePlanError(
                "Runtime planning requires an exact verified Spine v3 bundle"
            )
        replay_verified_spine42_v3_bundle(bundle)
        skeleton = bundle.skeleton_json
        semantics = derive_runtime_capture_plan_semantics(
            skeleton, bundle.clip_id, ticks_per_second=TICKS_PER_SECOND,
            max_composite_cases=MAX_COMPOSITE_CASES,
            max_setup_attachments=MAX_SETUP_ATTACHMENTS,
            max_capture_artifacts=MAX_CAPTURE_ARTIFACTS,
        )
        profile = spine42_v3_runtime_profile()
        body = {
            "format": PLAN_FORMAT,
            "format_version": PLAN_VERSION,
            "profile_sha256": spine42_v3_runtime_profile_sha256(),
            "source": {
                "project_id": bundle.project_id,
                "clip_id": bundle.clip_id,
                "skeleton_json_sha256": bundle.skeleton_json_sha256,
                "bundle_sha256": bundle.bundle_sha256,
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
    except Spine42V3RuntimePlanError:
        raise
    except (
        AttributeError, KeyError, OverflowError, TypeError,
        UnicodeError, ValueError,
    ) as exc:
        raise Spine42V3RuntimePlanError(
            f"Spine v3 runtime capture planning failed: {exc}"
        ) from exc


def spine42_v3_runtime_plan_sha256(plan: Mapping[str, Any]) -> str:
    """Recompute and require the domain-separated plan identity."""

    try:
        body = json.loads(canonical_spine42_v3_runtime_plan_bytes(plan))
        supplied = body.pop("capture_plan_sha256", None)
        result = canonical_sha256({"domain": PLAN_HASH_DOMAIN, **body})
        if supplied != result:
            raise Spine42V3RuntimePlanError(
                "Runtime capture plan digest is inconsistent"
            )
        return result
    except Spine42V3RuntimePlanError:
        raise
    except (AttributeError, TypeError, ValueError) as exc:
        raise Spine42V3RuntimePlanError(
            "Runtime capture plan cannot be hashed"
        ) from exc


def canonical_spine42_v3_runtime_plan_bytes(
    value: Mapping[str, Any],
) -> bytes:
    """Serialize a plan-shaped mapping as stable strict JSON bytes."""

    if not isinstance(value, Mapping):
        raise Spine42V3RuntimePlanError("Runtime capture plan must be an object")
    try:
        return json.dumps(
            dict(value), ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
    except (OverflowError, TypeError, UnicodeError, ValueError) as exc:
        raise Spine42V3RuntimePlanError(
            "Runtime capture plan is not strict finite JSON"
        ) from exc


__all__ = [
    "PLAN_FORMAT", "PLAN_VERSION", "Spine42V3RuntimePlanError",
    "build_spine42_v3_runtime_plan",
    "canonical_spine42_v3_runtime_plan_bytes",
    "spine42_v3_runtime_plan_sha256",
]
