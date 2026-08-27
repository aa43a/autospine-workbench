"""Current-review-head boundary shared by P10.7 compile and store."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .body_sway_dynamic_seam_head_checks import (
    BodySwayDynamicSeamHeadObservation,
    require_current_body_sway_dynamic_seam_heads,
)
from .motion_instance_v3_bundle_integrity import VerifiedMotionInstanceV3Bundle
from .motion_instance_v3_bundle_reader import VerifiedMotionInstanceV3BundleReader


class Spine42V3CurrentHeadsError(RuntimeError):
    """Raised when P10.7 cannot bind one stable reviewed source."""


def load_motion_instance_v3_and_dynamic_source(
    state_root: Path,
    project_id: str,
    motion_instance_v3_sha256: str,
    motion_instance_v3_bundle_sha256: str,
) -> tuple[VerifiedMotionInstanceV3Bundle, Mapping[str, Any]]:
    """Replay one exact MIv3 and extract its admitted dynamic source."""

    try:
        verified = VerifiedMotionInstanceV3BundleReader(Path(state_root)).load(
            project_id,
            motion_instance_v3_sha256,
            motion_instance_v3_bundle_sha256,
        )
        admission = verified.document(
            "body-sway-motion-consumer-admission.json"
        )
        source = admission["source"]["body_sway_dynamic_seam_probe"][
            "source"
        ]
        if type(source) is not dict:
            raise Spine42V3CurrentHeadsError(
                "MotionInstance v3 dynamic source is invalid"
            )
        return verified, source
    except Spine42V3CurrentHeadsError:
        raise
    except (AttributeError, KeyError, RuntimeError, TypeError, ValueError) as exc:
        raise Spine42V3CurrentHeadsError(
            "MotionInstance v3 source closure could not be replayed"
        ) from exc


def observe_spine42_v3_current_heads(
    state_root: Path,
    source: Mapping[str, Any],
) -> BodySwayDynamicSeamHeadObservation:
    """Observe the two mutable review heads for one exact dynamic source."""

    try:
        return require_current_body_sway_dynamic_seam_heads(
            Path(state_root), source
        )
    except (RuntimeError, TypeError, ValueError) as exc:
        raise Spine42V3CurrentHeadsError(
            "Spine v3 current review heads could not be observed"
        ) from exc


def require_same_spine42_v3_heads(before, after) -> None:
    """Reject any observed identity or canonical-evidence drift."""

    if type(before) is not BodySwayDynamicSeamHeadObservation \
            or type(after) is not BodySwayDynamicSeamHeadObservation \
            or before.identity != after.identity \
            or before.canonical_bytes != after.canonical_bytes:
        raise Spine42V3CurrentHeadsError(
            "Spine v3 current review heads drifted"
        )


__all__ = [
    "Spine42V3CurrentHeadsError",
    "load_motion_instance_v3_and_dynamic_source",
    "observe_spine42_v3_current_heads",
    "require_same_spine42_v3_heads",
]
