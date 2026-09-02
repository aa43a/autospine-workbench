"""P10.7a v2 source adapter and current-review-head boundary."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .body_sway_dynamic_seam_head_checks_v2 import (
    BodySwayDynamicSeamHeadCheckV2Error,
    BodySwayDynamicSeamHeadObservationV2,
    require_current_body_sway_dynamic_seam_heads_v2,
)
from .motion_instance_v3_bundle_reader_v2 import (
    MotionInstanceV3BundleReaderV2,
    MotionInstanceV3BundleReaderV2Error,
    VerifiedMotionInstanceV3BundleV2,
)
from .project_store import ProjectStore


class Spine42V3CurrentHeadsV2Error(RuntimeError):
    """Raised when P10.7a v2 cannot bind one stable reviewed source."""


def load_motion_instance_v3_v2_and_dynamic_source(
    state_root: Path,
    project_id: str,
    motion_instance_v3_sha256: str,
    motion_instance_v3_bundle_sha256: str,
) -> tuple[VerifiedMotionInstanceV3BundleV2, Mapping[str, Any]]:
    """Replay one exact v2-source MIv3 and extract its dynamic source."""

    try:
        verified = MotionInstanceV3BundleReaderV2(Path(state_root)).load(
            project_id, motion_instance_v3_sha256,
            motion_instance_v3_bundle_sha256,
        )
        admission = verified.document(
            "body-sway-motion-consumer-admission-v2.json"
        )
        source = admission["source"][
            "body_sway_dynamic_seam_probe_v2"
        ]["source"]
        if type(source) is not dict:
            raise Spine42V3CurrentHeadsV2Error(
                "P10.7a v2 dynamic source is invalid"
            )
        return verified, source
    except Spine42V3CurrentHeadsV2Error:
        raise
    except (
        AttributeError, KeyError, MotionInstanceV3BundleReaderV2Error,
        OSError, RuntimeError, TypeError, ValueError,
    ) as exc:
        raise Spine42V3CurrentHeadsV2Error(
            "P10.7a v2 source closure could not be replayed"
        ) from exc


def observe_spine42_v3_current_heads_v2(
    capture_job_reader,
    project_store: ProjectStore,
    source: Mapping[str, Any],
) -> BodySwayDynamicSeamHeadObservationV2:
    """Observe current visual-v2 and seam-v1 heads for an exact source."""

    try:
        return require_current_body_sway_dynamic_seam_heads_v2(
            capture_job_reader, project_store, source,
        )
    except (BodySwayDynamicSeamHeadCheckV2Error, RuntimeError,
            TypeError, ValueError) as exc:
        raise Spine42V3CurrentHeadsV2Error(
            "P10.7a v2 current review heads could not be observed"
        ) from exc


def require_same_spine42_v3_heads_v2(before, after) -> None:
    """Reject identity or canonical-evidence drift between observations."""

    if type(before) is not BodySwayDynamicSeamHeadObservationV2 \
            or type(after) is not BodySwayDynamicSeamHeadObservationV2 \
            or before.identity_sha256 != after.identity_sha256 \
            or before.canonical_bytes != after.canonical_bytes:
        raise Spine42V3CurrentHeadsV2Error(
            "P10.7a v2 current review heads drifted"
        )


__all__ = [
    "Spine42V3CurrentHeadsV2Error",
    "load_motion_instance_v3_v2_and_dynamic_source",
    "observe_spine42_v3_current_heads_v2",
    "require_same_spine42_v3_heads_v2",
]
