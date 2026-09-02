"""Bounded detached P10.6a v2 replay used by P10.6b preparation."""

from __future__ import annotations

import json
from typing import Any

from .body_sway_motion_consumer_admission_v2 import (
    BodySwayMotionConsumerAdmissionCoreV2,
    BodySwayMotionConsumerAdmissionV2Error,
    observation_from_document_v2,
    seal_body_sway_motion_consumer_admission_v2,
)
from .body_sway_motion_consumer_profile_v2 import (
    MAX_DOCUMENT_BYTES,
    MAX_DOCUMENT_JSON_DEPTH,
    MAX_DOCUMENT_JSON_NODES,
)
from .seam_anchor_review_json import (
    canonical_json_bytes,
    require_bounded_json_tree,
)


class MotionInstanceV3PreparedCheckV2Error(ValueError):
    """Raised when detached admission replay is invalid or inconsistent."""


def bounded_body_sway_admission_v2(value: Any) -> dict[str, Any]:
    """Return a bounded canonical object copy of one admission."""

    try:
        require_bounded_json_tree(
            value, max_nodes=MAX_DOCUMENT_JSON_NODES,
            max_depth=MAX_DOCUMENT_JSON_DEPTH,
        )
        encoded = canonical_json_bytes(value)
        if len(encoded) > MAX_DOCUMENT_BYTES:
            raise MotionInstanceV3PreparedCheckV2Error(
                "P10.6a v2 admission exceeds its byte limit"
            )
        copied = json.loads(encoded)
        if type(copied) is not dict:
            raise MotionInstanceV3PreparedCheckV2Error(
                "P10.6a v2 admission must be an exact JSON object"
            )
        return copied
    except MotionInstanceV3PreparedCheckV2Error:
        raise
    except (
        OverflowError, RecursionError, TypeError, UnicodeError, ValueError,
    ) as exc:
        raise MotionInstanceV3PreparedCheckV2Error(
            f"P10.6a v2 admission JSON is invalid: {exc}"
        ) from exc


def body_sway_admission_observations_v2(
    core: BodySwayMotionConsumerAdmissionCoreV2,
    document: Any,
):
    """Rebuild the two typed observations embedded by an exact admission."""

    try:
        root = bounded_body_sway_admission_v2(document)
        heads = root["head_observations"]
        return (
            observation_from_document_v2(
                core, heads["before"]["observation"],
            ),
            observation_from_document_v2(
                core, heads["after"]["observation"],
            ),
        )
    except MotionInstanceV3PreparedCheckV2Error:
        raise
    except (
        AttributeError, BodySwayMotionConsumerAdmissionV2Error, KeyError,
        OverflowError, RecursionError, TypeError, UnicodeError, ValueError,
    ) as exc:
        raise MotionInstanceV3PreparedCheckV2Error(
            f"P10.6a v2 admission observations are invalid: {exc}"
        ) from exc


def replay_body_sway_admission_with_core_v2(
    core: BodySwayMotionConsumerAdmissionCoreV2,
    document: Any,
) -> bytes:
    """Replay exact admission bytes without re-reading P10.5d or P9."""

    root = bounded_body_sway_admission_v2(document)
    before, after = body_sway_admission_observations_v2(core, root)
    try:
        expected = seal_body_sway_motion_consumer_admission_v2(
            core, before, after,
        )
        if expected.canonical_bytes != canonical_json_bytes(root):
            raise MotionInstanceV3PreparedCheckV2Error(
                "P10.6a v2 admission differs from prepared-core replay"
            )
        return expected.canonical_bytes
    except MotionInstanceV3PreparedCheckV2Error:
        raise
    except BodySwayMotionConsumerAdmissionV2Error as exc:
        raise MotionInstanceV3PreparedCheckV2Error(
            f"P10.6a v2 detached replay failed: {exc}"
        ) from exc


__all__ = [
    "MotionInstanceV3PreparedCheckV2Error",
    "body_sway_admission_observations_v2",
    "bounded_body_sway_admission_v2",
    "replay_body_sway_admission_with_core_v2",
]
