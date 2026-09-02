"""Version-neutral bounded in-memory collector for runtime PNG artifacts."""

from __future__ import annotations

import json
import threading
from types import MappingProxyType
from typing import Any, Callable

from .png_rgba import RgbaPngError, decode_rgba_png
from .spine42_v3_runtime_capture_report import (
    base_report, capture_report, png_dimensions,
    require_capture_snapshot_consistency,
)
from .spine42_v3_runtime_session_core import canonical_json, copy_json


MAX_CAPTURE_BYTES = 4 * 1024 * 1024
MAX_CAPTURE_TOTAL_BYTES = 128 * 1024 * 1024
MAX_RUNTIME_ERROR_CHARACTERS = 1000


class RuntimeCaptureCollectorCore:
    """Collect one terminal result per exact, ordered artifact session."""

    def __init__(
        self, sessions, *, error_type: type[ValueError],
        snapshot_factory: Callable[[str, tuple[tuple[str, bytes], ...]], Any],
    ) -> None:
        self._error = error_type
        self._snapshot_factory = snapshot_factory
        try:
            artifact_ids = sessions.artifact_ids
            if not artifact_ids or len(artifact_ids) != len(set(artifact_ids)):
                raise error_type(
                    "Runtime artifact inventory is empty or duplicated"
                )
            supplied = sessions.session_bytes
            if type(supplied) is not dict \
                    or tuple(supplied) != artifact_ids:
                raise error_type(
                    "Runtime session byte inventory differs from artifact order"
                )
            session_items = []
            for artifact_id, raw in supplied.items():
                if type(raw) is not bytes:
                    raise error_type("Runtime session bytes are invalid")
                session = json.loads(raw)
                if canonical_json(session).encode("utf-8") != raw \
                        or session.get("artifact", {}).get(
                            "artifact_id"
                        ) != artifact_id:
                    raise error_type("Runtime session bytes are not canonical")
                require_fixed_capture(
                    session, error_type=error_type,
                )
                session_items.append((artifact_id, raw))
        except error_type:
            raise
        except (
            AttributeError, KeyError, TypeError, UnicodeError, ValueError,
        ) as exc:
            raise error_type(f"Runtime sessions are invalid: {exc}") from exc
        self._artifact_ids = artifact_ids
        self._session_set_sha256 = sessions.sha256
        self._session_bytes = MappingProxyType(dict(session_items))
        self._reports: dict[str, dict[str, Any]] = {}
        self._captures: dict[str, bytes] = {}
        self._inflight: set[str] = set()
        self._total_bytes = 0
        self._reserved_bytes = 0
        self._lock = threading.Lock()
        self._decode_slot = threading.BoundedSemaphore(1)

    @property
    def artifact_ids(self) -> tuple[str, ...]:
        return self._artifact_ids

    @property
    def session_set_sha256(self) -> str:
        return self._session_set_sha256

    def session(self, artifact_id: str) -> dict[str, Any]:
        self._require_artifact_id(artifact_id)
        return json.loads(self._session_bytes[artifact_id])

    def record_capture(
        self, artifact_id: str, png_bytes: bytes, *,
        device_pixel_ratio: int, observed_inventory: dict[str, Any],
    ) -> dict[str, Any]:
        session = self.session(artifact_id)
        require_observed_inventory(
            observed_inventory, session["expected_observables"],
            error_type=self._error,
        )
        if type(png_bytes) is not bytes \
                or not 0 < len(png_bytes) <= MAX_CAPTURE_BYTES:
            raise self._error(
                "Runtime capture must be a bounded PNG byte snapshot"
            )
        if type(device_pixel_ratio) is not int or device_pixel_ratio != 1:
            raise self._error(
                "Runtime capture DPR differs from the fixed DPR1 profile"
            )
        if png_dimensions(png_bytes, error_type=self._error) != (640, 640):
            raise self._error(
                "Runtime capture dimensions differ from 640x640"
            )
        if not self._decode_slot.acquire(blocking=False):
            raise self._error(
                "Another runtime capture is already being decoded"
            )
        reserved = False
        try:
            with self._lock:
                self._require_pending(artifact_id)
                projected = (
                    self._total_bytes + self._reserved_bytes + len(png_bytes)
                )
                if projected > MAX_CAPTURE_TOTAL_BYTES:
                    raise self._error(
                        "Runtime capture set exceeds its total byte limit"
                    )
                self._inflight.add(artifact_id)
                self._reserved_bytes += len(png_bytes)
                reserved = True
            try:
                image = decode_rgba_png(
                    png_bytes, source_name=f"{artifact_id}.png",
                )
            except RgbaPngError as exc:
                raise self._error(
                    f"Runtime capture PNG is invalid: {exc}"
                ) from exc
            if (image.width, image.height) != (640, 640):
                raise self._error(
                    "Runtime capture decoded dimensions changed"
                )
            report = capture_report(
                session, png_bytes, image.width, image.height,
                observed_inventory,
            )
            with self._lock:
                self._finish_reservation(artifact_id, len(png_bytes))
                reserved = False
                self._captures[artifact_id] = png_bytes
                self._reports[artifact_id] = copy_json(report)
                self._total_bytes += len(png_bytes)
            return copy_json(report)
        finally:
            if reserved:
                with self._lock:
                    self._finish_reservation(artifact_id, len(png_bytes))
            self._decode_slot.release()

    def record_error(self, artifact_id: str, message: str) -> dict[str, Any]:
        session = self.session(artifact_id)
        if type(message) is not str or not message \
                or len(message) > MAX_RUNTIME_ERROR_CHARACTERS:
            raise self._error("Runtime error message is invalid")
        try:
            message.encode("utf-8")
        except UnicodeError as exc:
            raise self._error(
                "Runtime error message is not valid UTF-8"
            ) from exc
        report = base_report(session, "runtime_error")
        report["message"] = message
        with self._lock:
            self._require_pending(artifact_id)
            self._reports[artifact_id] = copy_json(report)
        return copy_json(report)

    def status(self) -> dict[str, Any]:
        with self._lock:
            captured, errors = self._terminal_artifact_ids()
        return {
            "expected_artifact_ids": list(self._artifact_ids),
            "captured_artifact_ids": captured,
            "error_artifact_ids": errors,
            "complete": captured == list(self._artifact_ids) and not errors,
        }

    def snapshot(self):
        with self._lock:
            captured, errors = self._terminal_artifact_ids()
            if captured != list(self._artifact_ids) or errors or self._inflight:
                raise self._error(
                    "Runtime capture set is incomplete or contains an error"
                )
            require_capture_snapshot_consistency(
                self._artifact_ids, self._session_bytes,
                self._captures, self._reports, error_type=self._error,
            )
            reports = [copy_json(self._reports[key])
                       for key in self._artifact_ids]
            items = tuple((key, self._captures[key])
                          for key in self._artifact_ids)
        return self._snapshot_factory(canonical_json(reports), items)

    def _require_artifact_id(self, artifact_id: str) -> None:
        if type(artifact_id) is not str or artifact_id not in self._session_bytes:
            raise self._error(
                "Artifact is absent from the exact runtime plan"
            )

    def _require_pending(self, artifact_id: str) -> None:
        if artifact_id in self._reports or artifact_id in self._inflight:
            raise self._error(
                "Runtime artifact already has a terminal or in-flight result"
            )

    def _finish_reservation(self, artifact_id: str, size: int) -> None:
        self._inflight.remove(artifact_id)
        self._reserved_bytes -= size

    def _terminal_artifact_ids(self) -> tuple[list[str], list[str]]:
        captured = [key for key in self._artifact_ids
                    if self._reports.get(key, {}).get("status") == "captured"]
        errors = [key for key in self._artifact_ids
                  if self._reports.get(key, {}).get("status") == "runtime_error"]
        return captured, errors

def require_fixed_capture(session, *, error_type) -> None:
    capture = session["capture"]
    if capture["viewport"] != {"width": 640, "height": 640} \
            or capture["device_pixel_ratio"] != 1 \
            or capture["preserve_drawing_buffer"] is not True:
        raise error_type(
            "Collector accepts only the fixed 640x640 DPR1 profile"
        )


def require_observed_inventory(value, expected, *, error_type) -> None:
    if type(value) is not dict or set(value) != {
        "official_runtime_loaded", "clip_ids", "slot_ids",
        "attachments", "isolation",
    }:
        raise error_type("Runtime observable inventory shape is invalid")
    try:
        detached = copy_json(value)
    except (OverflowError, TypeError, UnicodeError, ValueError) as exc:
        raise error_type(
            "Runtime observable inventory is not strict JSON"
        ) from exc
    if detached != expected:
        raise error_type(
            "Runtime observable inventory differs from the exact bundle"
        )


__all__ = [
    "MAX_CAPTURE_BYTES", "MAX_CAPTURE_TOTAL_BYTES",
    "MAX_RUNTIME_ERROR_CHARACTERS", "RuntimeCaptureCollectorCore",
]
