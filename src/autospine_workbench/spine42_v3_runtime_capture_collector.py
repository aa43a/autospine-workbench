"""Bounded fail-closed collector for P10.7b browser raster evidence."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import struct
import threading
from typing import Any

from .png_rgba import RgbaPngError, decode_rgba_png
from .spine42_v3_runtime_session import Spine42V3RuntimeSessions


MAX_CAPTURE_BYTES = 4 * 1024 * 1024
MAX_CAPTURE_TOTAL_BYTES = 128 * 1024 * 1024
MAX_RUNTIME_ERROR_CHARACTERS = 1000
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

class Spine42V3RuntimeCaptureCollectorError(ValueError):
    """Raised for missing, duplicated, malformed, or unbounded evidence."""


@dataclass(frozen=True, slots=True)
class Spine42V3RuntimeCaptureSnapshot:
    """Complete ordered reports and immutable captured PNG byte snapshots."""

    _reports_json: str = field(repr=False)
    _capture_items: tuple[tuple[str, bytes], ...] = field(repr=False)

    @property
    def reports(self) -> tuple[dict[str, Any], ...]:
        return tuple(json.loads(self._reports_json))

    @property
    def capture_bytes(self) -> dict[str, bytes]:
        return dict(self._capture_items)

class Spine42V3RuntimeCaptureCollector:
    """Accept one terminal result for every artifact in the exact plan."""

    def __init__(self, sessions: Spine42V3RuntimeSessions) -> None:
        if type(sessions) is not Spine42V3RuntimeSessions:
            raise Spine42V3RuntimeCaptureCollectorError(
                "Collector requires a frozen runtime session set"
            )
        try:
            artifact_ids = sessions.artifact_ids
            if not artifact_ids or len(artifact_ids) != len(set(artifact_ids)):
                raise Spine42V3RuntimeCaptureCollectorError(
                    "Runtime artifact inventory is empty or duplicated"
                )
            for artifact_id in artifact_ids:
                session = sessions.session(artifact_id)
                _require_fixed_capture(session)
        except Spine42V3RuntimeCaptureCollectorError:
            raise
        except (
            AttributeError, KeyError, TypeError, UnicodeError, ValueError,
        ) as exc:
            raise Spine42V3RuntimeCaptureCollectorError(
                f"Runtime sessions are invalid: {exc}"
            ) from exc
        self._sessions = sessions
        self._artifact_ids = artifact_ids
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
        return self._sessions.sha256

    def session(self, artifact_id: str) -> dict[str, Any]:
        self._require_artifact_id(artifact_id)
        return self._sessions.session(artifact_id)
    def record_capture(
        self,
        artifact_id: str,
        png_bytes: bytes,
        *,
        device_pixel_ratio: int,
        observed_inventory: dict[str, Any],
    ) -> dict[str, Any]:
        session = self.session(artifact_id)
        _require_observed_inventory(
            observed_inventory, session["expected_observables"]
        )
        if type(png_bytes) is not bytes \
                or not 0 < len(png_bytes) <= MAX_CAPTURE_BYTES:
            raise Spine42V3RuntimeCaptureCollectorError(
                "Runtime capture must be a bounded PNG byte snapshot"
            )
        if type(device_pixel_ratio) is not int \
                or device_pixel_ratio != 1:
            raise Spine42V3RuntimeCaptureCollectorError(
                "Runtime capture DPR differs from the fixed DPR1 profile"
            )
        if _png_dimensions(png_bytes) != (640, 640):
            raise Spine42V3RuntimeCaptureCollectorError(
                "Runtime capture dimensions differ from 640x640"
            )
        if not self._decode_slot.acquire(blocking=False):
            raise Spine42V3RuntimeCaptureCollectorError(
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
                    raise Spine42V3RuntimeCaptureCollectorError(
                        "Runtime capture set exceeds its total byte limit"
                    )
                self._inflight.add(artifact_id)
                self._reserved_bytes += len(png_bytes)
                reserved = True
            try:
                image = decode_rgba_png(
                    png_bytes, source_name=f"{artifact_id}.png"
                )
            except RgbaPngError as exc:
                raise Spine42V3RuntimeCaptureCollectorError(
                    f"Runtime capture PNG is invalid: {exc}"
                ) from exc
            if (image.width, image.height) != (640, 640):
                raise Spine42V3RuntimeCaptureCollectorError(
                    "Runtime capture decoded dimensions changed"
                )
            report = _capture_report(
                session, png_bytes, image.width, image.height,
                observed_inventory,
            )
            with self._lock:
                self._finish_reservation(artifact_id, len(png_bytes))
                reserved = False
                self._captures[artifact_id] = png_bytes
                self._reports[artifact_id] = _copy(report)
                self._total_bytes += len(png_bytes)
            return _copy(report)
        finally:
            if reserved:
                with self._lock:
                    self._finish_reservation(artifact_id, len(png_bytes))
            self._decode_slot.release()

    def record_error(self, artifact_id: str, message: str) -> dict[str, Any]:
        session = self.session(artifact_id)
        if type(message) is not str or not message \
                or len(message) > MAX_RUNTIME_ERROR_CHARACTERS:
            raise Spine42V3RuntimeCaptureCollectorError(
                "Runtime error message is invalid"
            )
        try:
            message.encode("utf-8")
        except UnicodeError as exc:
            raise Spine42V3RuntimeCaptureCollectorError(
                "Runtime error message is not valid UTF-8"
            ) from exc
        report = _base_report(session, "runtime_error")
        report["message"] = message
        with self._lock:
            self._require_pending(artifact_id)
            self._reports[artifact_id] = _copy(report)
        return _copy(report)

    def status(self) -> dict[str, Any]:
        with self._lock:
            captured, errors = self._terminal_artifact_ids()
        return {
            "expected_artifact_ids": list(self._artifact_ids),
            "captured_artifact_ids": captured,
            "error_artifact_ids": errors,
            "complete": captured == list(self._artifact_ids) and not errors,
        }

    def snapshot(self) -> Spine42V3RuntimeCaptureSnapshot:
        with self._lock:
            captured, errors = self._terminal_artifact_ids()
            if captured != list(self._artifact_ids) or errors or self._inflight:
                raise Spine42V3RuntimeCaptureCollectorError(
                    "Runtime capture set is incomplete or contains an error"
                )
            reports = [_copy(self._reports[key]) for key in self._artifact_ids]
            items = tuple(
                (key, self._captures[key])
                for key in self._artifact_ids
            )
        return Spine42V3RuntimeCaptureSnapshot(_canonical(reports), items)

    def _require_artifact_id(self, artifact_id: str) -> None:
        if type(artifact_id) is not str or artifact_id not in self._artifact_ids:
            raise Spine42V3RuntimeCaptureCollectorError(
                "Artifact is absent from the exact runtime plan"
            )

    def _require_pending(self, artifact_id: str) -> None:
        if artifact_id in self._reports or artifact_id in self._inflight:
            raise Spine42V3RuntimeCaptureCollectorError(
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


def _require_fixed_capture(session) -> None:
    capture = session["capture"]
    if capture["viewport"] != {"width": 640, "height": 640} \
            or capture["device_pixel_ratio"] != 1 \
            or capture["preserve_drawing_buffer"] is not True:
        raise Spine42V3RuntimeCaptureCollectorError(
            "Collector accepts only the fixed 640x640 DPR1 profile"
        )


def _require_observed_inventory(value, expected) -> None:
    if type(value) is not dict or set(value) != {
        "official_runtime_loaded", "clip_ids", "slot_ids",
        "attachments", "isolation",
    }:
        raise Spine42V3RuntimeCaptureCollectorError(
            "Runtime observable inventory shape is invalid"
        )
    try:
        detached = _copy(value)
    except (OverflowError, TypeError, UnicodeError, ValueError) as exc:
        raise Spine42V3RuntimeCaptureCollectorError(
            "Runtime observable inventory is not strict JSON"
        ) from exc
    if detached != expected:
        raise Spine42V3RuntimeCaptureCollectorError(
            "Runtime observable inventory differs from the exact bundle"
        )


def _png_dimensions(raw: bytes) -> tuple[int, int]:
    if len(raw) < 24 or raw[:8] != _PNG_SIGNATURE \
            or raw[12:16] != b"IHDR":
        raise Spine42V3RuntimeCaptureCollectorError(
            "Runtime capture is not a canonical PNG header"
        )
    return struct.unpack(">II", raw[16:24])


def _base_report(session, status):
    return {
        "status": status,
        "session_set_sha256": session["session_set_sha256"],
        "plan_sha256": session["plan_sha256"],
        "source": session["source"], "runtime": session["runtime"],
        "assets": session["assets"], "capture": session["capture"],
        "case": session["case"], "artifact": session["artifact"],
    }


def _capture_report(session, raw, width, height, observed):
    report = _base_report(session, "captured")
    report["observables"] = _copy(observed)
    report["image"] = {
        "path": session["artifact"]["path"],
        "png_sha256": hashlib.sha256(raw).hexdigest(),
        "width": width, "height": height, "size_bytes": len(raw),
    }
    return report

def _copy(value: Any) -> dict[str, Any]:
    return json.loads(_canonical(value))


def _canonical(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    )


__all__ = [
    "Spine42V3RuntimeCaptureCollector",
    "Spine42V3RuntimeCaptureCollectorError",
    "Spine42V3RuntimeCaptureSnapshot",
]
