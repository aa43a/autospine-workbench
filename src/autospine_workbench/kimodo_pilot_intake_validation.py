"""Strict validation for a path-free real Kimodo pilot intake report."""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
import math
import re
from types import MappingProxyType
from typing import Any

from .kimodo_npz_consistency import (
    HEADING_NORM_TOLERANCE,
    MATRIX_CROSSCHECK_TOLERANCE,
    POSITION_CROSSCHECK_METERS,
)
from .kimodo_npz_source import MAX_RAW_NPZ_BYTES


FORMAT = "autospine-kimodo-pilot-intake-report"
FORMAT_VERSION = 1
REPORT_DOMAIN = "autospine-kimodo-pilot-intake-report/v1"
MAX_REPORT_BYTES = 64 * 1024
MAX_EXTERNAL_PROVENANCE_BYTES = 4 * 1024 * 1024

CLAIMS = MappingProxyType({
    "raw_npz_and_external_provenance_bytes_bound": True,
    "canonical_json_input_identities_bound": True,
    "p7_structural_compile_passed": True,
    "p8_camera_input_admitted": True,
    "checkpoint_authenticity_verified": False,
    "motion_quality_approved": False,
    "p8_projection_emitted": False,
    "p9_reviewed": False,
    "release_authority": False,
})
AUTHORITY = MappingProxyType({
    "state_mutation": False,
    "latest_selection": False,
    "pipeline_publication": False,
    "human_decision": False,
    "publish": False,
    "release": False,
})
STATUS = "eligible_for_p7_p8_compile"

_SHA256 = re.compile(r"[0-9a-f]{64}")
_REVISION = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})")
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_TOP = {
    "format", "format_version", "source", "producer", "p7_preview",
    "p8_input", "claims", "authority", "status", "intake_report_sha256",
}
_SOURCE = {
    "raw_npz_sha256", "raw_npz_byte_length", "source_sha256", "source_id",
    "map_sha256", "map_id", "clip_id", "camera_sha256", "camera_id",
    "checkpoint_manifest_sha256", "checkpoint_manifest_byte_length",
    "generation_request_sha256", "generation_request_byte_length",
}
_PRODUCER = {
    "implementation", "repository_revision", "model_id",
    "checkpoint_revision", "seed", "sample_index",
}
_P7 = {
    "compiler_id", "compiler_version", "motion_ir_sha256",
    "compile_run_sha256", "array_inventory_sha256", "validation",
}
_METRICS = {
    "max_global_matrix_error", "max_heading_norm_error",
    "max_position_error_meters", "max_root_position_error_meters",
}
_P8 = {
    "camera_map_binding", "projection", "depth_positive",
}


class KimodoPilotIntakeValidationError(ValueError):
    """Raised when an intake report loses evidence or overstates authority."""


def kimodo_pilot_intake_report_sha256(value: Mapping[str, Any]) -> str:
    """Return the domain-separated content identity, excluding its hash field."""

    body = _snapshot(value)
    body.pop("intake_report_sha256", None)
    envelope = {"domain": REPORT_DOMAIN, "value": body}
    return hashlib.sha256(_canonical(envelope)).hexdigest()


def require_kimodo_pilot_intake_report(value: Mapping[str, Any]) -> None:
    """Require the exact v1 report shape, derived constants, and self hash."""

    try:
        root = _object(value, _TOP, "report")
        if root["format"] != FORMAT \
                or type(root["format_version"]) is not int \
                or root["format_version"] != FORMAT_VERSION:
            _fail("Kimodo pilot intake report version is invalid")
        _source(root["source"])
        _producer(root["producer"])
        _p7(root["p7_preview"])
        _p8(root["p8_input"])
        if type(root["claims"]) is not dict \
                or type(root["authority"]) is not dict \
                or not _same_json(root["claims"], dict(CLAIMS)) \
                or not _same_json(root["authority"], dict(AUTHORITY)) \
                or root["status"] != STATUS:
            _fail("Kimodo pilot intake derived authority is invalid")
        _sha(root["intake_report_sha256"], "report")
        if root["intake_report_sha256"] != \
                kimodo_pilot_intake_report_sha256(root):
            _fail("Kimodo pilot intake report self hash is invalid")
        if len(_canonical(root)) > MAX_REPORT_BYTES:
            _fail("Kimodo pilot intake report byte limit exceeded")
    except KimodoPilotIntakeValidationError:
        raise
    except (KeyError, OverflowError, RecursionError, TypeError, ValueError) as exc:
        raise KimodoPilotIntakeValidationError(
            "Kimodo pilot intake report validation failed"
        ) from exc


def _source(value: Any) -> None:
    row = _object(value, _SOURCE, "source")
    for field in (
        "raw_npz_sha256", "source_sha256", "map_sha256", "camera_sha256",
        "checkpoint_manifest_sha256", "generation_request_sha256",
    ):
        _sha(row[field], field)
    for field in ("source_id", "map_id", "clip_id", "camera_id"):
        _token(row[field], field)
    limits = {
        "raw_npz_byte_length": MAX_RAW_NPZ_BYTES,
        "checkpoint_manifest_byte_length": MAX_EXTERNAL_PROVENANCE_BYTES,
        "generation_request_byte_length": MAX_EXTERNAL_PROVENANCE_BYTES,
    }
    for field, maximum in limits.items():
        number = row[field]
        if type(number) is not int or not 1 <= number <= maximum:
            _fail("Kimodo pilot intake source byte length is invalid")


def _producer(value: Any) -> None:
    row = _object(value, _PRODUCER, "producer")
    if row["implementation"] != "nv-tlabs/kimodo":
        _fail("Kimodo pilot intake producer is invalid")
    for field in ("repository_revision", "checkpoint_revision"):
        if not isinstance(row[field], str) or not _REVISION.fullmatch(row[field]):
            _fail("Kimodo pilot intake producer revision is invalid")
    _token(row["model_id"], "model_id")
    if type(row["seed"]) is not int or not -(2 ** 63) <= row["seed"] < 2 ** 63 \
            or type(row["sample_index"]) is not int \
            or not 0 <= row["sample_index"] <= 1_000_000:
        _fail("Kimodo pilot intake producer index is invalid")


def _p7(value: Any) -> None:
    row = _object(value, _P7, "P7 preview")
    if row["compiler_id"] != "kimodo-npz-motionir-compiler" \
            or row["compiler_version"] != "1.1.0":
        _fail("Kimodo pilot intake P7 compiler identity is invalid")
    for field in (
        "motion_ir_sha256", "compile_run_sha256", "array_inventory_sha256",
    ):
        _sha(row[field], field)
    metrics = _object(row["validation"], _METRICS, "P7 validation")
    limits = {
        "max_global_matrix_error": MATRIX_CROSSCHECK_TOLERANCE,
        "max_heading_norm_error": HEADING_NORM_TOLERANCE,
        "max_position_error_meters": POSITION_CROSSCHECK_METERS,
        "max_root_position_error_meters": POSITION_CROSSCHECK_METERS,
    }
    for field, maximum in limits.items():
        number = metrics[field]
        if field == "max_heading_norm_error" and number is None:
            continue
        if isinstance(number, bool) or not isinstance(number, (int, float)) \
                or not math.isfinite(number) or not 0 <= number <= maximum:
            _fail("Kimodo pilot intake P7 validation metric is invalid")


def _p8(value: Any) -> None:
    row = _object(value, _P8, "P8 input")
    if row["camera_map_binding"] != "verified" \
            or row["projection"] != "static_orthographic" \
            or row["depth_positive"] not in {
                "toward_camera", "away_from_camera",
            }:
        _fail("Kimodo pilot intake P8 input is invalid")


def _object(value: Any, fields: set[str], label: str) -> Mapping[str, Any]:
    if type(value) is not dict or set(value) != fields:
        _fail(f"Kimodo pilot intake {label} fields are invalid")
    return value


def _sha(value: Any, label: str) -> None:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        _fail(f"Kimodo pilot intake {label} SHA-256 is invalid")


def _token(value: Any, label: str) -> None:
    if not isinstance(value, str) or not _TOKEN.fullmatch(value):
        _fail(f"Kimodo pilot intake {label} is invalid")


def _snapshot(value: Mapping[str, Any]) -> dict[str, Any]:
    result = json.loads(_canonical(value))
    if type(result) is not dict:
        _fail("Kimodo pilot intake report must be an object")
    return result


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")


def _same_json(left: Any, right: Any) -> bool:
    return _canonical(left) == _canonical(right)


def _fail(message: str) -> None:
    raise KimodoPilotIntakeValidationError(message)


__all__ = [
    "AUTHORITY", "CLAIMS", "FORMAT", "FORMAT_VERSION",
    "KimodoPilotIntakeValidationError", "MAX_EXTERNAL_PROVENANCE_BYTES",
    "STATUS",
    "kimodo_pilot_intake_report_sha256",
    "require_kimodo_pilot_intake_report",
]
