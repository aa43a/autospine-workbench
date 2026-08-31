"""Spine 4.2 preview adapter for current human-reviewed capture framing."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any

from .body_sway_preview_inputs_v2 import BodySwayPreviewInputsV2
from .body_sway_preview_profile_v2 import (
    SKELETON_HASH_DIGEST_DOMAIN,
    body_sway_preview_adapter_profile_v2,
)
from .body_sway_preview_projection_v2 import (
    BodySwayPreviewProjectionV2,
    BodySwayPreviewProjectionV2Error,
    body_sway_preview_setup_sha256_v2,
    compile_body_sway_preview_projection_v2,
)
from .resolved_project import canonical_sha256
from .spine42_body_sway_preview_adapter import (
    Spine42BodySwayPreviewAdapterError,
    compile_spine42_body_sway_preview,
)
from .spine42_contract import canonical_spine42_json


class Spine42BodySwayPreviewAdapterV2Error(ValueError):
    """Raised when v2 framing cannot wrap the exact legacy Spine preview."""


@dataclass(frozen=True, slots=True)
class Spine42BodySwayPreviewV2:
    projection: BodySwayPreviewProjectionV2
    _skeleton_json: str

    @property
    def skeleton_json(self) -> dict[str, Any]:
        return json.loads(self._skeleton_json)

    @property
    def skeleton_bytes(self) -> bytes:
        return self._skeleton_json.encode("utf-8")

    @property
    def skeleton_sha256(self) -> str:
        return hashlib.sha256(self.skeleton_bytes).hexdigest()


def body_sway_preview_skeleton_hash_v2(
    *, rig_sha256, target_profile_sha256,
    motion_instance_v2_sha256, body_sway_probe_report_sha256,
    preview_projection_sha256, capture_framing_candidate_sha256,
    capture_framing_decision_sha256, world_viewport,
) -> str:
    """Recompute the v2 Spine skeleton metadata hash from detached seals."""

    return canonical_sha256({
        "domain": SKELETON_HASH_DIGEST_DOMAIN,
        "adapter_profile": body_sway_preview_adapter_profile_v2(),
        "rig_sha256": rig_sha256,
        "target_profile_sha256": target_profile_sha256,
        "motion_instance_v2_sha256": motion_instance_v2_sha256,
        "body_sway_probe_report_sha256": body_sway_probe_report_sha256,
        "preview_projection_sha256": preview_projection_sha256,
        "capture_framing_candidate_sha256":
            capture_framing_candidate_sha256,
        "capture_framing_decision_sha256":
            capture_framing_decision_sha256,
        "world_viewport": dict(world_viewport),
    })


def compile_spine42_body_sway_preview_v2(
    inputs: BodySwayPreviewInputsV2,
) -> Spine42BodySwayPreviewV2:
    """Change only framing metadata/hash around the exact v1 preview payload."""

    if type(inputs) is not BodySwayPreviewInputsV2:
        raise Spine42BodySwayPreviewAdapterV2Error(
            "Spine body-sway preview v2 requires exact admitted inputs v2"
        )
    try:
        legacy = compile_spine42_body_sway_preview(
            inputs.legacy_projection_inputs()
        )
        projection = compile_body_sway_preview_projection_v2(inputs)
        if projection.document["legacy_projection_sha256"] \
                != legacy.projection.sha256:
            raise Spine42BodySwayPreviewAdapterV2Error(
                "Preview v2 projection differs from the legacy mathematics"
            )
        document = legacy.skeleton_json
        viewport = inputs.world_viewport
        document["skeleton"].update({
            "x": viewport["x"], "y": viewport["y"],
            "width": viewport["width"], "height": viewport["height"],
        })
        probe = inputs.probe_inputs
        document["skeleton"]["hash"] = body_sway_preview_skeleton_hash_v2(
            rig_sha256=canonical_sha256(probe.rig),
            target_profile_sha256=canonical_sha256(probe.target_profile),
            motion_instance_v2_sha256=
                canonical_sha256(probe.motion_instance_v2),
            body_sway_probe_report_sha256=inputs.report_sha256,
            preview_projection_sha256=projection.sha256,
            capture_framing_candidate_sha256=
                inputs.framing_candidate_sha256,
            capture_framing_decision_sha256=
                inputs.framing_decision_sha256,
            world_viewport=viewport,
        )
        if body_sway_preview_setup_sha256_v2(document) \
                != projection.document["setup_sha256"]:
            raise Spine42BodySwayPreviewAdapterV2Error(
                "Preview v2 setup differs from the framed projection"
            )
        encoded = canonical_spine42_json(document)
        return Spine42BodySwayPreviewV2(
            projection, encoded.decode("utf-8"),
        )
    except Spine42BodySwayPreviewAdapterV2Error:
        raise
    except (
        BodySwayPreviewProjectionV2Error,
        Spine42BodySwayPreviewAdapterError,
        KeyError, OverflowError, TypeError, UnicodeError, ValueError,
    ) as exc:
        raise Spine42BodySwayPreviewAdapterV2Error(
            f"Spine body-sway preview v2 compilation failed: {exc}"
        ) from exc
