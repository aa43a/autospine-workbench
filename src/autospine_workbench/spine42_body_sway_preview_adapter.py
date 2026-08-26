"""Pure exact-input adapter for a two-animation temporary Spine 4.2 preview."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any

from .body_sway_preview_inputs import BodySwayPreviewInputs
from .body_sway_preview_profile import (
    BASE_ANIMATION_NAME,
    COMBINED_ANIMATION_NAME,
    body_sway_preview_adapter_profile,
)
from .body_sway_preview_projection import (
    BodySwayPreviewProjection,
    BodySwayPreviewProjectionError,
    compile_body_sway_preview_projection,
)
from .resolved_project import canonical_sha256
from .spine42_contract import canonical_spine42_json
from .spine42_contract_v2 import Spine42ContractV2Error
from .spine42_json_adapter_v2 import build_spine42_json_v2
from .spine42_timeline_projection import (
    Spine42TimelineProjectionError,
    project_spine42_motion,
)


class Spine42BodySwayPreviewAdapterError(ValueError):
    """Raised when exact preview inputs cannot form temporary Spine JSON."""


@dataclass(frozen=True, slots=True)
class Spine42BodySwayPreview:
    """Frozen projection plus canonical two-animation Spine JSON bytes."""

    projection: BodySwayPreviewProjection
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


def compile_spine42_body_sway_preview(
    inputs: BodySwayPreviewInputs,
) -> Spine42BodySwayPreview:
    """Compile base and sampled-linear sway clips without a release contract."""

    if type(inputs) is not BodySwayPreviewInputs:
        raise Spine42BodySwayPreviewAdapterError(
            "Spine body-sway preview requires exact admitted inputs"
        )
    try:
        projection = compile_body_sway_preview_projection(inputs)
        probe = inputs.probe_inputs
        rig = probe.rig
        motion = probe.motion_instance_v2
        target = probe.target_profile
        document = build_spine42_json_v2(
            rig, motion_instance=motion, target_profile=target
        )
        base_animation = document["animations"].pop(motion["clip_id"])
        combined_source = {
            "timing": motion["timing"],
            "tracks": [
                *projection.rotation_tracks,
                *[row for row in motion["tracks"]
                  if row["property"] == "translation"],
            ],
            "markers": motion["markers"],
            "draw_order": motion["draw_order"],
        }
        events, combined_animation = project_spine42_motion(
            combined_source, document["slots"]
        )
        if events != document["events"]:
            raise Spine42BodySwayPreviewAdapterError(
                "Combined preview events differ from exact MotionInstance v2"
            )
        document["animations"] = {
            BASE_ANIMATION_NAME: base_animation,
            COMBINED_ANIMATION_NAME: combined_animation,
        }
        document["skeleton"]["hash"] = canonical_sha256({
            "adapter_profile": body_sway_preview_adapter_profile(),
            "rig_sha256": canonical_sha256(rig),
            "target_profile_sha256": canonical_sha256(target),
            "motion_instance_v2_sha256": canonical_sha256(motion),
            "body_sway_probe_report_sha256": inputs.report_sha256,
            "preview_projection_sha256": projection.sha256,
        })
        encoded = canonical_spine42_json(document)
        return Spine42BodySwayPreview(
            projection, encoded.decode("utf-8")
        )
    except Spine42BodySwayPreviewAdapterError:
        raise
    except (
        BodySwayPreviewProjectionError, Spine42ContractV2Error,
        Spine42TimelineProjectionError, KeyError, OverflowError,
        TypeError, UnicodeError, ValueError,
    ) as exc:
        raise Spine42BodySwayPreviewAdapterError(
            f"Spine body-sway preview compilation failed: {exc}"
        ) from exc
