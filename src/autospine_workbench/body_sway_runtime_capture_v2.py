"""Frozen detached RuntimeCapture v2 value and exact Preview v2 bridge."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any

from .body_sway_runtime_capture_v2_validation import (
    BodySwayRuntimeCaptureV2ValidationError,
    require_body_sway_runtime_capture_v2,
)
from .resolved_project import canonical_sha256


class BodySwayRuntimeCaptureV2Error(ValueError):
    """Raised when v2 capture bytes or their exact preview binding differ."""


@dataclass(frozen=True, slots=True)
class BodySwayRuntimeCaptureV2:
    """Validated PNG payload awaiting execution; it grants no evidence authority."""

    _canonical_json: str = field(repr=False)
    _capture_items: tuple[tuple[str, bytes], ...] = field(repr=False)

    @classmethod
    def from_detached(
        cls, document: dict[str, Any], capture_bytes: dict[str, bytes],
    ) -> "BodySwayRuntimeCaptureV2":
        """Validate complete detached bytes without claiming upstream currentness."""

        try:
            require_body_sway_runtime_capture_v2(document, capture_bytes)
            return cls(_canonical(document), tuple(sorted(capture_bytes.items())))
        except BodySwayRuntimeCaptureV2ValidationError as exc:
            raise BodySwayRuntimeCaptureV2Error(
                "Detached runtime capture v2 is invalid"
            ) from exc

    @property
    def document(self) -> dict[str, Any]:
        return json.loads(self._canonical_json)

    @property
    def canonical_bytes(self) -> bytes:
        return self._canonical_json.encode("utf-8")

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes).hexdigest()

    @property
    def capture_bytes(self) -> dict[str, bytes]:
        return dict(self._capture_items)

    @property
    def artifact_set_sha256(self) -> str:
        return self.document["artifacts"]["artifact_set_sha256"]


def require_body_sway_runtime_capture_v2_preview_binding(
    capture: BodySwayRuntimeCaptureV2, preview: Any,
) -> None:
    """Bind v2 evidence to an exact validated TemporaryBodySwayPreviewV2.

    The import is intentionally local so this storage boundary stays usable while
    the independently versioned Preview v2 compiler is assembled.
    """

    try:
        from .temporary_body_sway_preview_v2 import TemporaryBodySwayPreviewV2
        from .temporary_body_sway_preview_validation_v2 import (
            require_temporary_body_sway_preview_v2,
        )

        if type(capture) is not BodySwayRuntimeCaptureV2 \
                or type(preview) is not TemporaryBodySwayPreviewV2:
            raise BodySwayRuntimeCaptureV2Error(
                "Runtime capture v2 requires exact preview and capture values"
            )
        require_body_sway_runtime_capture_v2(
            capture.document, capture.capture_bytes
        )
        preview_document = preview.document
        require_temporary_body_sway_preview_v2(
            preview_document, preview.artifact_bytes
        )
        source = capture.document["source"]
        preview_source = preview_document["source"]
        projection = preview_document["projection"]
        plan = preview_document["capture_plan"]
        framing = {
            "capture_framing_candidate_sha256":
                preview_source["capture_framing_candidate_sha256"],
            "capture_framing_decision_sha256":
                preview_source["capture_framing_decision_sha256"],
            "capture_framing_revision":
                preview_source["capture_framing_revision"],
            "world_viewport": plan["world_viewport"],
        }
        projection_framing = {
            field: projection[field] for field in framing
        }
        plan_source = plan["source"]
        expected_plan_source = {
            "preview_projection_sha256": projection["projection_sha256"],
            "capture_framing_candidate_sha256":
                framing["capture_framing_candidate_sha256"],
            "capture_framing_decision_sha256":
                framing["capture_framing_decision_sha256"],
            "capture_framing_revision": framing["capture_framing_revision"],
        }
        if projection_framing != framing \
                or plan_source != expected_plan_source:
            raise BodySwayRuntimeCaptureV2Error(
                "Preview v2 source, projection, and capture-plan seals differ"
            )
        files = {row["role"]: row for row in preview_document["artifacts"]["files"]}
        expected_assets = {
            "skeleton_sha256": files["spine-skeleton-v2"]["sha256"],
            "atlas_sha256": files["spine-atlas"]["sha256"],
            "texture_sha256": files["spine-texture"]["sha256"],
            "texture_size": [
                preview_document["summary"]["atlas_width"],
                preview_document["summary"]["atlas_height"],
            ],
        }
        current_head = preview_source["current_p10_1_head"]
        expected = {
            "temporary_preview_v2_sha256": preview.sha256,
            "preview_artifact_set_sha256": preview.artifact_set_sha256,
            "preview_projection_v2_sha256": projection["projection_sha256"],
            "capture_plan_v2_sha256": plan["capture_plan_sha256"],
            "preview_source_sha256": canonical_sha256(preview_source),
            "body_sway_probe_report_sha256":
                preview_source["body_sway_probe_report_sha256"],
            "current_p10_1_head": current_head,
            **framing,
        }
        capture_document = capture.document
        if any(source.get(field) != value for field, value in expected.items()) \
                or capture_document["assets"] != expected_assets \
                or capture_document["capture"]["cases"] != plan["cases"] \
                or any(
                    capture_document["capture"].get(field) != plan[field]
                    for field in (
                        "viewport", "device_pixel_ratio", "background",
                        "preserve_drawing_buffer", "world_viewport",
                    )
                ):
            raise BodySwayRuntimeCaptureV2Error(
                "Runtime capture v2 differs from exact Preview v2 identities"
            )
    except BodySwayRuntimeCaptureV2Error:
        raise
    except (
        AttributeError, ImportError, KeyError, OverflowError,
        TypeError, UnicodeError, ValueError,
    ) as exc:
        raise BodySwayRuntimeCaptureV2Error(
            f"Runtime capture v2 preview binding failed: {exc}"
        ) from exc


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      sort_keys=True, separators=(",", ":"))
