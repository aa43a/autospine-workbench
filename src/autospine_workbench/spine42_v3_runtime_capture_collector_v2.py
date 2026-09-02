"""Bounded fail-closed collector for version-isolated P10.7b v2 sessions."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any

from .spine42_v3_runtime_capture_core import (
    MAX_CAPTURE_BYTES, MAX_CAPTURE_TOTAL_BYTES,
    MAX_RUNTIME_ERROR_CHARACTERS, RuntimeCaptureCollectorCore,
)
from .spine42_v3_runtime_session_v2 import Spine42V3RuntimeSessionsV2


class Spine42V3RuntimeCaptureCollectorV2Error(ValueError):
    """Raised for invalid or incomplete v2 runtime raster evidence."""


@dataclass(frozen=True, slots=True)
class Spine42V3RuntimeCaptureSnapshotV2:
    _reports_json: str = field(repr=False)
    _capture_items: tuple[tuple[str, bytes], ...] = field(repr=False)

    @property
    def reports(self) -> tuple[dict[str, Any], ...]:
        return tuple(json.loads(self._reports_json))

    @property
    def capture_bytes(self) -> dict[str, bytes]:
        return dict(self._capture_items)


class Spine42V3RuntimeCaptureCollectorV2:
    """Accept exactly one result for every artifact in a v2 session set."""

    def __init__(self, sessions: Spine42V3RuntimeSessionsV2) -> None:
        if type(sessions) is not Spine42V3RuntimeSessionsV2:
            raise Spine42V3RuntimeCaptureCollectorV2Error(
                "Collector v2 requires a frozen runtime session set v2"
            )
        self._core = RuntimeCaptureCollectorCore(
            sessions, error_type=Spine42V3RuntimeCaptureCollectorV2Error,
            snapshot_factory=Spine42V3RuntimeCaptureSnapshotV2,
        )

    @property
    def artifact_ids(self) -> tuple[str, ...]:
        return self._core.artifact_ids

    @property
    def session_set_sha256(self) -> str:
        return self._core.session_set_sha256

    def session(self, artifact_id: str) -> dict[str, Any]:
        return self._core.session(artifact_id)

    def record_capture(
        self, artifact_id: str, png_bytes: bytes, *,
        device_pixel_ratio: int, observed_inventory: dict[str, Any],
    ) -> dict[str, Any]:
        return self._core.record_capture(
            artifact_id, png_bytes,
            device_pixel_ratio=device_pixel_ratio,
            observed_inventory=observed_inventory,
        )

    def record_error(self, artifact_id: str, message: str) -> dict[str, Any]:
        return self._core.record_error(artifact_id, message)

    def status(self) -> dict[str, Any]:
        return self._core.status()

    def snapshot(self) -> Spine42V3RuntimeCaptureSnapshotV2:
        return self._core.snapshot()


__all__ = [
    "MAX_CAPTURE_BYTES", "MAX_CAPTURE_TOTAL_BYTES",
    "MAX_RUNTIME_ERROR_CHARACTERS", "Spine42V3RuntimeCaptureCollectorV2",
    "Spine42V3RuntimeCaptureCollectorV2Error",
    "Spine42V3RuntimeCaptureSnapshotV2",
]
