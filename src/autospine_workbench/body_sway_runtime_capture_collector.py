"""Bounded in-memory browser capture collector for P10 runtime evidence."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import struct
import threading
from typing import Any

from .body_sway_runtime_capture_session import (
    BodySwayRuntimeCaptureSessions,
)
from .body_sway_runtime_capture_session_validation import (
    require_body_sway_runtime_capture_session_set,
)
from .png_rgba import RgbaPngError, decode_rgba_png


MAX_CAPTURE_BYTES = 4 * 1024 * 1024
MAX_CAPTURE_TOTAL_BYTES = 128 * 1024 * 1024
MAX_RUNTIME_ERROR_CHARACTERS = 1000
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class BodySwayRuntimeCaptureCollectorError(ValueError):
    """Raised when browser evidence is missing, duplicated, or unbounded."""


@dataclass(frozen=True, slots=True)
class BodySwayRuntimeCaptureSnapshot:
    """Complete immutable per-case reports and exact PNG bytes."""

    _reports_json: str = field(repr=False)
    _capture_items: tuple[tuple[str, bytes], ...] = field(repr=False)

    @property
    def reports(self) -> tuple[dict[str, Any], ...]:
        return tuple(json.loads(self._reports_json))

    @property
    def capture_bytes(self) -> dict[str, bytes]:
        return dict(self._capture_items)


class BodySwayRuntimeCaptureCollector:
    """Accept at most one terminal browser result for every fixed case."""

    def __init__(self, sessions: BodySwayRuntimeCaptureSessions) -> None:
        try:
            if type(sessions) is not BodySwayRuntimeCaptureSessions:
                raise BodySwayRuntimeCaptureCollectorError(
                    "Collector requires a frozen complete session set"
                )
            require_body_sway_runtime_capture_session_set(sessions.document)
            self._sessions = sessions
            self._case_ids = sessions.case_ids
        except BodySwayRuntimeCaptureCollectorError:
            raise
        except (
            AttributeError, KeyError, OverflowError, RecursionError,
            TypeError, UnicodeError, ValueError,
        ) as exc:
            raise BodySwayRuntimeCaptureCollectorError(
                f"Runtime capture sessions are invalid: {exc}"
            ) from exc
        self._reports: dict[str, dict[str, Any]] = {}
        self._captures: dict[str, bytes] = {}
        self._inflight: set[str] = set()
        self._total_bytes = 0
        self._reserved_bytes = 0
        self._lock = threading.Lock()
        self._decode_slot = threading.BoundedSemaphore(1)

    @property
    def case_ids(self) -> tuple[str, ...]:
        return self._case_ids

    @property
    def session_set_sha256(self) -> str:
        return self._sessions.sha256

    def session(self, case_id: str) -> dict[str, Any]:
        self._require_case_id(case_id)
        return self._sessions.session(case_id)

    def record_capture(
        self, case_id: str, png_bytes: bytes, *, device_pixel_ratio: int,
    ) -> dict[str, Any]:
        session = self.session(case_id)
        if type(png_bytes) is not bytes \
                or not 0 < len(png_bytes) <= MAX_CAPTURE_BYTES:
            raise BodySwayRuntimeCaptureCollectorError(
                "Runtime capture must be a bounded PNG byte snapshot"
            )
        expected_dpr = session["capture"]["device_pixel_ratio"]
        if type(device_pixel_ratio) is not int \
                or device_pixel_ratio != expected_dpr:
            raise BodySwayRuntimeCaptureCollectorError(
                "Runtime capture DPR differs from its exact session"
            )
        viewport = session["capture"]["viewport"]
        expected_size = (
            viewport["width"] * expected_dpr,
            viewport["height"] * expected_dpr,
        )
        if _png_dimensions(png_bytes) != expected_size:
            raise BodySwayRuntimeCaptureCollectorError(
                "Runtime capture dimensions differ from the fixed viewport"
            )
        if not self._decode_slot.acquire(blocking=False):
            raise BodySwayRuntimeCaptureCollectorError(
                "Another runtime capture is already being decoded"
            )
        reserved = False
        try:
            with self._lock:
                self._require_pending(case_id)
                projected = (
                    self._total_bytes + self._reserved_bytes + len(png_bytes)
                )
                if projected > MAX_CAPTURE_TOTAL_BYTES:
                    raise BodySwayRuntimeCaptureCollectorError(
                        "Runtime capture set exceeds its total byte limit"
                    )
                self._inflight.add(case_id)
                self._reserved_bytes += len(png_bytes)
                reserved = True
            try:
                image = decode_rgba_png(
                    png_bytes, source_name=f"{case_id}.png"
                )
            except RgbaPngError as exc:
                raise BodySwayRuntimeCaptureCollectorError(
                    f"Runtime capture PNG is invalid: {exc}"
                ) from exc
            if (image.width, image.height) != expected_size:
                raise BodySwayRuntimeCaptureCollectorError(
                    "Runtime capture decoded dimensions changed"
                )
            report = _report(
                session, self.session_set_sha256, png_bytes,
                image.width, image.height,
            )
            with self._lock:
                self._finish_reservation(case_id, len(png_bytes))
                reserved = False
                self._captures[case_id] = png_bytes
                self._reports[case_id] = _copy(report)
                self._total_bytes += len(png_bytes)
            return _copy(report)
        finally:
            if reserved:
                with self._lock:
                    self._finish_reservation(case_id, len(png_bytes))
            self._decode_slot.release()

    def record_error(self, case_id: str, message: str) -> dict[str, Any]:
        session = self.session(case_id)
        if type(message) is not str or not message \
                or len(message) > MAX_RUNTIME_ERROR_CHARACTERS:
            raise BodySwayRuntimeCaptureCollectorError(
                "Runtime error message is invalid"
            )
        try:
            message.encode("utf-8")
        except UnicodeError as exc:
            raise BodySwayRuntimeCaptureCollectorError(
                "Runtime error message is not valid UTF-8"
            ) from exc
        report = {
            "status": "runtime_error",
            "project_id": session["project_id"],
            "clip_id": session["clip_id"],
            "session_set_sha256": self.session_set_sha256,
            "runtime": session["runtime"], "source": session["source"],
            "assets": session["assets"], "capture": session["capture"],
            "case": session["case"], "message": message,
        }
        with self._lock:
            self._require_pending(case_id)
            self._reports[case_id] = _copy(report)
        return _copy(report)

    def status(self) -> dict[str, Any]:
        with self._lock:
            captured, errors = self._terminal_case_ids()
        return {
            "expected_case_ids": list(self._case_ids),
            "captured_case_ids": captured,
            "error_case_ids": errors,
            "complete": captured == list(self._case_ids),
        }

    def snapshot(self) -> BodySwayRuntimeCaptureSnapshot:
        with self._lock:
            captured, errors = self._terminal_case_ids()
            if captured != list(self._case_ids) or errors or self._inflight:
                raise BodySwayRuntimeCaptureCollectorError(
                    "Runtime capture set is incomplete or contains an error"
                )
            reports = [_copy(self._reports[key]) for key in self._case_ids]
            items = tuple(
                (f"captures/{key}.png", self._captures[key])
                for key in self._case_ids
            )
        return BodySwayRuntimeCaptureSnapshot(_canonical(reports), items)

    def _require_case_id(self, case_id: str) -> None:
        if type(case_id) is not str or case_id not in self._case_ids:
            raise BodySwayRuntimeCaptureCollectorError(
                "Capture case is absent from the exact plan"
            )

    def _require_pending(self, case_id: str) -> None:
        if case_id in self._reports or case_id in self._inflight:
            raise BodySwayRuntimeCaptureCollectorError(
                "Runtime capture case already has a terminal or in-flight result"
            )

    def _finish_reservation(self, case_id: str, size: int) -> None:
        self._inflight.remove(case_id)
        self._reserved_bytes -= size

    def _terminal_case_ids(self) -> tuple[list[str], list[str]]:
        captured = [
            key for key in self._case_ids
            if self._reports.get(key, {}).get("status") == "captured"
        ]
        errors = [
            key for key in self._case_ids
            if self._reports.get(key, {}).get("status") == "runtime_error"
        ]
        return captured, errors


def _png_dimensions(raw: bytes) -> tuple[int, int]:
    if len(raw) < 24 or raw[:8] != _PNG_SIGNATURE \
            or raw[12:16] != b"IHDR":
        raise BodySwayRuntimeCaptureCollectorError(
            "Runtime capture is not a canonical PNG header"
        )
    return struct.unpack(">II", raw[16:24])


def _report(session, session_set_sha256, raw, width, height):
    return {
        "status": "captured",
        "project_id": session["project_id"], "clip_id": session["clip_id"],
        "session_set_sha256": session_set_sha256,
        "runtime": session["runtime"], "source": session["source"],
        "assets": session["assets"], "capture": session["capture"],
        "case": session["case"],
        "image": {
            "path": f"captures/{session['case']['id']}.png",
            "png_sha256": hashlib.sha256(raw).hexdigest(),
            "width": width, "height": height, "size_bytes": len(raw),
        },
    }


def _copy(value: Any) -> dict[str, Any]:
    return json.loads(_canonical(value))


def _canonical(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    )
