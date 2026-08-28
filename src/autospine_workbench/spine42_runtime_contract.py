"""Pinned local-runtime and screenshot contracts for the Spine 4.2 gate."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import json
import math
import re
from typing import Any

from .spine42_contract import SPINE_RUNTIME_PACKAGE, SPINE_RUNTIME_VERSION
from .spine42_runtime_inputs import Spine42ExportFiles


RUNTIME_NPM_INTEGRITY = (
    "sha512-hcbg1xaTq5DHjeLmyMP90YX8p0A9v4G1cS3Xp4tD+MDw/"
    "reVqJhL2O/8NbTnOlc6lQvc8Vi9S1JjYyIILgWm3Q=="
)
SESSION_FORMAT = "autospine-spine42-runtime-session"
GOLDEN_FORMAT = "autospine-spine42-runtime-golden"
FORMAT_VERSION = 1
DEFAULT_BACKGROUND = "#20242aff"
DEFAULT_VIEWPORT = (640, 640)
DEFAULT_DPR = 1
DEFAULT_CASE = {"id": "setup", "clip": None, "time_seconds": 0.0}

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_RGBA = re.compile(r"^#[0-9a-fA-F]{8}$")
_APPROVED_PNG = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]{0,111}\.approved\.png$"
)
_WINDOWS_DEVICES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


class Spine42RuntimeContractError(ValueError):
    """Raised when runtime evidence cannot satisfy the pinned P6 contract."""


def build_runtime_session(
    exports: Spine42ExportFiles,
    *,
    viewport: tuple[int, int] = DEFAULT_VIEWPORT,
    device_pixel_ratio: int = DEFAULT_DPR,
    background: str = DEFAULT_BACKGROUND,
    case: Mapping[str, Any] = DEFAULT_CASE,
) -> dict[str, Any]:
    """Build the browser-visible immutable session description."""

    width, height = _viewport(viewport)
    dpr = _dpr(device_pixel_ratio)
    if not isinstance(background, str) or not _RGBA.fullmatch(background):
        raise Spine42RuntimeContractError("background must be #RRGGBBAA")
    normalized_case = _case(case)
    return {
        "format": SESSION_FORMAT,
        "format_version": FORMAT_VERSION,
        "runtime": {
            "package": SPINE_RUNTIME_PACKAGE,
            "version": SPINE_RUNTIME_VERSION,
            "npm_integrity": RUNTIME_NPM_INTEGRITY,
        },
        "assets": {
            "skeleton_sha256": exports.skeleton_sha256,
            "atlas_sha256": exports.atlas_sha256,
            "texture_sha256": exports.texture_sha256,
            "texture_size": list(exports.texture_size),
        },
        "capture": {
            "viewport": {"width": width, "height": height},
            "device_pixel_ratio": dpr,
            "background": background.lower(),
            "preserve_drawing_buffer": True,
            "world_viewport": dict(exports.world_viewport),
        },
        "case": normalized_case,
    }


def require_runtime_golden(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a screenshot golden contract and return a detached copy."""

    value = _mapping(value, "runtime golden")
    _fields(
        value,
        {"format", "format_version", "runtime", "capture", "cases"},
        "runtime golden",
    )
    if value.get("format") != GOLDEN_FORMAT \
            or type(value.get("format_version")) is not int \
            or value.get("format_version") != 1:
        raise Spine42RuntimeContractError("runtime golden format is unsupported")
    runtime = _mapping(value.get("runtime"), "golden runtime")
    _fields(runtime, {"package", "version", "npm_integrity"}, "golden runtime")
    expected_runtime = (SPINE_RUNTIME_PACKAGE, SPINE_RUNTIME_VERSION, RUNTIME_NPM_INTEGRITY)
    if tuple(runtime.get(key) for key in ("package", "version", "npm_integrity")) != expected_runtime:
        raise Spine42RuntimeContractError("golden runtime identity is not exact")
    capture = _mapping(value.get("capture"), "golden capture")
    _fields(
        capture,
        {"viewport", "device_pixel_ratio", "background"},
        "golden capture",
    )
    viewport = _mapping(capture.get("viewport"), "golden viewport")
    _fields(viewport, {"width", "height"}, "golden viewport")
    _viewport((viewport.get("width"), viewport.get("height")))
    _dpr(capture.get("device_pixel_ratio"))
    if not isinstance(capture.get("background"), str) or not _RGBA.fullmatch(capture["background"]):
        raise Spine42RuntimeContractError("golden background must be #RRGGBBAA")
    cases = _suite_cases(value.get("cases"))
    for item in cases:
        original = next(raw for raw in value["cases"] if raw.get("id") == item["id"])
        _fields(
            original,
            {"id", "clip", "time_seconds", "assets", "golden", "thresholds"},
            "runtime case",
        )
        assets = _mapping(original.get("assets"), "case assets")
        _fields(
            assets,
            {"skeleton_sha256", "atlas_sha256", "texture_sha256"},
            "case assets",
        )
        for key in ("skeleton_sha256", "atlas_sha256", "texture_sha256"):
            if not isinstance(assets.get(key), str) or not _SHA256.fullmatch(assets[key]):
                raise Spine42RuntimeContractError(f"case {key} is invalid")
        golden = _mapping(original.get("golden"), "case golden")
        _fields(golden, {"path", "png_sha256"}, "case golden")
        path = golden.get("path")
        prefix = path.split(".", 1)[0].upper() if isinstance(path, str) else ""
        if not isinstance(path, str) or not _APPROVED_PNG.fullmatch(path) \
                or ".." in path or prefix in _WINDOWS_DEVICES:
            raise Spine42RuntimeContractError("golden PNG path must be a safe approved basename")
        if not isinstance(golden.get("png_sha256"), str) or not _SHA256.fullmatch(golden["png_sha256"]):
            raise Spine42RuntimeContractError("golden PNG SHA-256 is invalid")
        thresholds = _mapping(original.get("thresholds"), "case thresholds")
        _fields(
            thresholds,
            {
                "max_differing_pixel_ratio",
                "max_mean_absolute_error",
                "max_channel_delta",
            },
            "case thresholds",
        )
        _ratio(thresholds.get("max_differing_pixel_ratio"), "differing pixel ratio")
        _range(thresholds.get("max_mean_absolute_error"), 0, 255, "mean absolute error")
        maximum = thresholds.get("max_channel_delta")
        if not isinstance(maximum, int) or isinstance(maximum, bool) or not 0 <= maximum <= 255:
            raise Spine42RuntimeContractError("max channel delta must be an integer in [0,255]")
    return json.loads(canonical_json_bytes(value))


def canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    try:
        return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                          separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise Spine42RuntimeContractError("contract is not canonical finite JSON") from exc


def _suite_cases(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) < 3:
        raise Spine42RuntimeContractError("runtime gate requires at least three capture cases")
    result: list[dict[str, Any]] = []
    ids: set[str] = set()
    clips: set[str | None] = set()
    for raw in value:
        item = _case(_mapping(raw, "runtime case"))
        if item["id"] in ids:
            raise Spine42RuntimeContractError("runtime case ids must be unique")
        ids.add(item["id"])
        clips.add(item["clip"])
        result.append(item)
    if clips != {None, "idle", "wave.left"}:
        raise Spine42RuntimeContractError("runtime cases must cover setup, idle, and wave.left")
    return result


def _case(raw: Mapping[str, Any]) -> dict[str, Any]:
    case_id, clip, time = raw.get("id"), raw.get("clip"), raw.get("time_seconds")
    if not isinstance(case_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9.-]{0,63}", case_id):
        raise Spine42RuntimeContractError("runtime case id is unsafe")
    if clip not in {None, "idle", "wave.left"}:
        raise Spine42RuntimeContractError("runtime case clip is invalid")
    if not isinstance(time, (int, float)) or isinstance(time, bool) or not math.isfinite(time) or time < 0:
        raise Spine42RuntimeContractError("runtime case time must be finite and non-negative")
    return {"id": case_id, "clip": clip, "time_seconds": float(time)}


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise Spine42RuntimeContractError(f"{label} must be an object")
    return value


def _fields(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise Spine42RuntimeContractError(f"{label} fields are invalid")


def _viewport(value: tuple[Any, Any]) -> tuple[int, int]:
    width, height = value
    if any(not isinstance(item, int) or isinstance(item, bool) or not 64 <= item <= 4096
           for item in (width, height)):
        raise Spine42RuntimeContractError("viewport dimensions must be integers in [64,4096]")
    return width, height


def _dpr(value: Any) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value not in {1, 2, 3, 4}:
        raise Spine42RuntimeContractError("device pixel ratio must be one of 1,2,3,4")
    return value


def _ratio(value: Any, label: str) -> float:
    return _range(value, 0, 1, label)


def _range(value: Any, low: float, high: float, label: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
        raise Spine42RuntimeContractError(f"{label} must be finite")
    if not low <= value <= high:
        raise Spine42RuntimeContractError(f"{label} is outside [{low},{high}]")
    return float(value)
