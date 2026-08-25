"""Capture persistence and pixel comparison for the Spine 4.2 runtime gate."""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
import threading
from typing import Any

from .png_rgba import RgbaPngError, decode_rgba_png
from .safe_input_files import SafeInputFileError, read_real_file
from .spine42_runtime_contract import (
    canonical_json_bytes,
    require_runtime_golden,
)


MAX_CAPTURE_BYTES = 64 * 1024 * 1024


class Spine42RuntimeRegressionError(ValueError):
    """Raised when a browser capture is unsafe or does not match its session."""


class Spine42CaptureStore:
    """Write only ``*.actual`` evidence; approved goldens remain immutable."""

    def __init__(
        self,
        output_root: Path,
        session: Mapping[str, Any],
        *,
        golden: Mapping[str, Any] | None = None,
        golden_root: Path | None = None,
    ) -> None:
        self.root = _output_directory(output_root)
        self.session = json.loads(canonical_json_bytes(session))
        self.case = self.session["case"]
        self.golden = require_runtime_golden(golden) if golden is not None else None
        if (self.golden is None) != (golden_root is None):
            raise Spine42RuntimeRegressionError(
                "golden contract and golden root must be supplied together"
            )
        self.golden_root = (
            _existing_directory(golden_root, "golden root") if golden_root else None
        )
        if self.golden is not None:
            self._match_golden_session()
        self._reports: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def record_capture(
        self, case_id: str, png_bytes: bytes, *, device_pixel_ratio: int
    ) -> dict[str, Any]:
        case = self._case(case_id)
        if not isinstance(png_bytes, bytes) or not 0 < len(png_bytes) <= MAX_CAPTURE_BYTES:
            raise Spine42RuntimeRegressionError("capture is not a bounded PNG byte snapshot")
        expected_dpr = self.session["capture"]["device_pixel_ratio"]
        if device_pixel_ratio != expected_dpr:
            raise Spine42RuntimeRegressionError("capture DPR differs from session")
        try:
            image = decode_rgba_png(png_bytes, source_name=f"{case_id}.actual.png")
        except RgbaPngError as exc:
            raise Spine42RuntimeRegressionError(f"invalid capture PNG: {exc}") from exc
        viewport = self.session["capture"]["viewport"]
        expected_size = (
            viewport["width"] * expected_dpr,
            viewport["height"] * expected_dpr,
        )
        if (image.width, image.height) != expected_size:
            raise Spine42RuntimeRegressionError("capture dimensions differ from fixed viewport")
        png_name = f"{case_id}.actual.png"
        report = {
            "format": "autospine-spine42-runtime-result",
            "format_version": 1,
            "runtime": self.session["runtime"],
            "assets": self.session["assets"],
            "capture": self.session["capture"],
            "case": case,
            "image": {
                "path": png_name,
                "png_sha256": _sha(png_bytes),
                "width": image.width,
                "height": image.height,
            },
            "comparison": self._compare(case_id, image),
        }
        _atomic_write(self.root / png_name, png_bytes)
        _atomic_write(
            self.root / f"{case_id}.actual.json", canonical_json_bytes(report)
        )
        with self._lock:
            self._reports[case_id] = report
        return json.loads(canonical_json_bytes(report))

    def record_error(self, case_id: str, message: str) -> dict[str, Any]:
        case = self._case(case_id)
        if not isinstance(message, str) or not message or len(message) > 1000:
            raise Spine42RuntimeRegressionError("runtime error message is invalid")
        report = {
            "format": "autospine-spine42-runtime-result",
            "format_version": 1,
            "runtime": self.session["runtime"],
            "assets": self.session["assets"],
            "capture": self.session["capture"],
            "case": case,
            "comparison": {"status": "runtime-error", "message": message},
        }
        _atomic_write(
            self.root / f"{case_id}.actual.json", canonical_json_bytes(report)
        )
        with self._lock:
            self._reports[case_id] = report
        return json.loads(canonical_json_bytes(report))

    def status(self) -> dict[str, Any]:
        with self._lock:
            reports = [self._reports[key] for key in sorted(self._reports)]
        expected = [self.case["id"]]
        captured = [item["case"]["id"] for item in reports]
        return {
            "expected_cases": expected,
            "captured_cases": captured,
            "complete": captured == expected,
            "reports": json.loads(canonical_json_bytes({"items": reports}))["items"],
        }

    def _case(self, case_id: str) -> dict[str, Any]:
        if not isinstance(case_id, str) or case_id != self.case["id"]:
            raise Spine42RuntimeRegressionError("unknown runtime capture case")
        return self.case

    def _match_golden_session(self) -> None:
        assert self.golden is not None
        if self.golden["runtime"] != self.session["runtime"]:
            raise Spine42RuntimeRegressionError("golden runtime differs from session")
        for key in ("viewport", "device_pixel_ratio", "background"):
            if self.golden["capture"][key] != self.session["capture"][key]:
                raise Spine42RuntimeRegressionError(f"golden capture {key} differs")
        golden_case = next(
            (item for item in self.golden["cases"] if item["id"] == self.case["id"]),
            None,
        )
        if golden_case is None:
            raise Spine42RuntimeRegressionError("session case is absent from golden suite")
        if (golden_case["clip"], golden_case["time_seconds"]) != (
            self.case["clip"], self.case["time_seconds"]
        ):
            raise Spine42RuntimeRegressionError("golden case differs from session")
        for key, value in golden_case["assets"].items():
            if key.endswith("_sha256") and self.session["assets"].get(key) != value:
                raise Spine42RuntimeRegressionError("golden assets differ from session")

    def _compare(self, case_id: str, actual: Any) -> dict[str, Any]:
        if self.golden is None or self.golden_root is None:
            return {"status": "not-configured"}
        golden_case = next(item for item in self.golden["cases"] if item["id"] == case_id)
        approved = self.golden_root / golden_case["golden"]["path"]
        try:
            approved_bytes = read_real_file(
                approved, MAX_CAPTURE_BYTES, "approved PNG"
            )
        except SafeInputFileError as exc:
            raise Spine42RuntimeRegressionError(
                "approved PNG snapshot is unsafe"
            ) from exc
        if _sha(approved_bytes) != golden_case["golden"]["png_sha256"]:
            raise Spine42RuntimeRegressionError("approved PNG SHA-256 changed")
        try:
            expected = decode_rgba_png(approved_bytes, source_name=approved.name)
        except RgbaPngError as exc:
            raise Spine42RuntimeRegressionError(f"invalid approved PNG: {exc}") from exc
        if (expected.width, expected.height) != (actual.width, actual.height):
            raise Spine42RuntimeRegressionError("approved PNG dimensions differ")
        metrics = _pixel_metrics(actual.pixels, expected.pixels)
        thresholds = golden_case["thresholds"]
        passed = (
            metrics["differing_pixel_ratio"] <= thresholds["max_differing_pixel_ratio"]
            and metrics["mean_absolute_error"] <= thresholds["max_mean_absolute_error"]
            and metrics["max_channel_delta"] <= thresholds["max_channel_delta"]
        )
        return {
            "status": "passed" if passed else "rejected",
            "approved_png_sha256": golden_case["golden"]["png_sha256"],
            "metrics": metrics,
            "thresholds": thresholds,
        }


def _pixel_metrics(actual: bytes, expected: bytes) -> dict[str, Any]:
    if len(actual) != len(expected) or len(actual) % 4:
        raise Spine42RuntimeRegressionError("RGBA buffers differ in length")
    differing_pixels = 0
    total_delta = 0
    max_delta = 0
    for offset in range(0, len(actual), 4):
        deltas = [abs(actual[offset + index] - expected[offset + index]) for index in range(4)]
        differing_pixels += int(any(deltas))
        total_delta += sum(deltas)
        max_delta = max(max_delta, *deltas)
    pixels = len(actual) // 4
    return {
        "differing_pixels": differing_pixels,
        "differing_pixel_ratio": differing_pixels / pixels,
        "mean_absolute_error": total_delta / len(actual),
        "max_channel_delta": max_delta,
    }


def _output_directory(path: Path) -> Path:
    path = Path(os.path.abspath(os.fspath(path)))
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise Spine42RuntimeRegressionError("cannot create capture directory") from exc
    return _existing_directory(path, "capture directory")


def _existing_directory(path: Path | None, label: str) -> Path:
    if path is None:
        raise Spine42RuntimeRegressionError(f"{label} is missing")
    candidate = Path(path)
    try:
        paths = (candidate, *candidate.parents)
        metadata = [(item, item.lstat()) for item in paths]
    except OSError as exc:
        raise Spine42RuntimeRegressionError(f"cannot inspect {label}") from exc
    if any(_is_alias(item, info) or not stat.S_ISDIR(info.st_mode)
           for item, info in metadata):
        raise Spine42RuntimeRegressionError(f"{label} must be a real directory")
    return candidate.resolve(strict=True)


def _is_alias(path: Path, metadata: os.stat_result) -> bool:
    if stat.S_ISLNK(metadata.st_mode):
        return True
    junction = getattr(path, "is_junction", None)
    if callable(junction) and junction():
        return True
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(getattr(metadata, "st_file_attributes", 0) & reparse)


def _atomic_write(path: Path, raw: bytes) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp_path = Path(temporary)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except OSError as exc:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise Spine42RuntimeRegressionError("cannot atomically write capture evidence") from exc


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()
