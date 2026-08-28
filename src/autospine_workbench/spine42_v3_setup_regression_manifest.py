"""Strict explicit request for the P10.7c setup-golden comparison."""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
from typing import Any

from .manifest_artifacts import (
    LayerManifestError,
    require_safe_token,
    require_sha256,
)
from .safe_input_files import SafeInputFileError, strict_json_object
from .spine42_v3_setup_regression_profile import COMPARISON_PROFILE_SHA256


FORMAT = "autospine-spine42-v3-setup-regression-request"
FORMAT_VERSION = 1
HASH_DOMAIN = "autospine-spine42-v3-setup-regression-request/v1"
MAX_REQUEST_BYTES = 64 * 1024
MAX_SAMPLES = 8
_ROOT_FIELDS = {
    "format", "format_version", "approved_p6_export_contract_sha256",
    "approved_runtime_golden_sha256", "comparison_profile_sha256", "samples",
}
_SAMPLE_FIELDS = {
    "project_id", "p6_setup_address", "spine42_v3_address",
    "runtime_capture_address", "approved_runtime_case_id",
    "approved_png_sha256", "p3_rig_sha256", "p3_bundle_sha256",
}
_RUNTIME_ADDRESS_FIELDS = {
    "spine42_v3_bundle_sha256", "capture_bundle_sha256",
}
_P6_ADDRESS_FIELDS = {"skeleton_json_sha256", "bundle_sha256"}
_SPINE_V3_ADDRESS_FIELDS = {"skeleton_json_sha256", "bundle_sha256"}


class Spine42V3SetupRegressionManifestError(ValueError):
    """Raised when a setup comparison request is ambiguous or unsafe."""


def parse_spine42_v3_setup_regression_request(
    data: bytes,
) -> dict[str, Any]:
    """Parse only the canonical UTF-8 representation of one request."""

    try:
        if type(data) is not bytes or not data or len(data) > MAX_REQUEST_BYTES:
            raise Spine42V3SetupRegressionManifestError(
                "Setup regression request bytes are invalid"
            )
        value = require_spine42_v3_setup_regression_request(
            strict_json_object(data, "setup regression request")
        )
        if data != canonical_request_bytes(value):
            raise Spine42V3SetupRegressionManifestError(
                "Setup regression request is not canonical JSON"
            )
        return value
    except Spine42V3SetupRegressionManifestError:
        raise
    except (LayerManifestError, SafeInputFileError, TypeError, ValueError) as exc:
        raise Spine42V3SetupRegressionManifestError(
            "Setup regression request could not be parsed"
        ) from exc


def require_spine42_v3_setup_regression_request(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate exact fields, ordering, identities, and sample uniqueness."""

    try:
        if type(value) is not dict or set(value) != _ROOT_FIELDS \
                or value.get("format") != FORMAT \
                or type(value.get("format_version")) is not int \
                or value.get("format_version") != FORMAT_VERSION:
            raise Spine42V3SetupRegressionManifestError(
                "Setup regression request root fields are invalid"
            )
        approved_export = require_sha256(
            value["approved_p6_export_contract_sha256"],
            "Approved P6 export contract",
        )
        approved_runtime = require_sha256(
            value["approved_runtime_golden_sha256"],
            "Approved runtime golden",
        )
        if value["comparison_profile_sha256"] != COMPARISON_PROFILE_SHA256:
            raise Spine42V3SetupRegressionManifestError(
                "Setup regression comparison profile is unsupported"
            )
        rows = value.get("samples")
        if type(rows) is not list or not 1 <= len(rows) <= MAX_SAMPLES:
            raise Spine42V3SetupRegressionManifestError(
                "Setup regression sample count is invalid"
            )
        samples = [_sample(row) for row in rows]
        ids = [row["project_id"] for row in samples]
        if ids != sorted(ids) or len(ids) != len(set(ids)):
            raise Spine42V3SetupRegressionManifestError(
                "Setup regression projects must be unique and ascending"
            )
        return _copy({
            "format": FORMAT,
            "format_version": FORMAT_VERSION,
            "approved_p6_export_contract_sha256": approved_export,
            "approved_runtime_golden_sha256": approved_runtime,
            "comparison_profile_sha256": COMPARISON_PROFILE_SHA256,
            "samples": samples,
        })
    except Spine42V3SetupRegressionManifestError:
        raise
    except (LayerManifestError, KeyError, TypeError, ValueError) as exc:
        raise Spine42V3SetupRegressionManifestError(
            "Setup regression request validation failed"
        ) from exc


def canonical_request_bytes(value: Mapping[str, Any]) -> bytes:
    """Return canonical bytes after complete semantic validation."""

    return _canonical(require_spine42_v3_setup_regression_request(value))


def setup_regression_request_sha256(value: Mapping[str, Any]) -> str:
    """Return the domain-separated identity of one request."""

    request = require_spine42_v3_setup_regression_request(value)
    return hashlib.sha256(_canonical({
        "domain": HASH_DOMAIN,
        "request": request,
    })).hexdigest()


def _sample(value: Any) -> dict[str, Any]:
    if type(value) is not dict or set(value) != _SAMPLE_FIELDS:
        raise Spine42V3SetupRegressionManifestError(
            "Setup regression sample fields are invalid"
        )
    runtime = value.get("runtime_capture_address")
    p6 = value.get("p6_setup_address")
    spine = value.get("spine42_v3_address")
    if type(runtime) is not dict or set(runtime) != _RUNTIME_ADDRESS_FIELDS \
            or type(p6) is not dict or set(p6) != _P6_ADDRESS_FIELDS \
            or type(spine) is not dict \
            or set(spine) != _SPINE_V3_ADDRESS_FIELDS:
        raise Spine42V3SetupRegressionManifestError(
            "Setup regression address fields are invalid"
        )
    case_id = require_safe_token(
        value["approved_runtime_case_id"], "Approved runtime case id"
    )
    if runtime["spine42_v3_bundle_sha256"] != spine["bundle_sha256"]:
        raise Spine42V3SetupRegressionManifestError(
            "Runtime capture is cross-wired to the Spine v3 bundle"
        )
    return {
        "project_id": require_safe_token(value["project_id"], "Project id"),
        "p3_rig_sha256": require_sha256(value["p3_rig_sha256"], "P3 rig"),
        "p3_bundle_sha256": require_sha256(
            value["p3_bundle_sha256"], "P3 bundle"
        ),
        "p6_setup_address": {
            field: require_sha256(p6[field], f"p6_setup_address.{field}")
            for field in sorted(_P6_ADDRESS_FIELDS)
        },
        "spine42_v3_address": {
            field: require_sha256(spine[field], f"spine42_v3_address.{field}")
            for field in sorted(_SPINE_V3_ADDRESS_FIELDS)
        },
        "runtime_capture_address": {
            field: require_sha256(runtime[field], field)
            for field in sorted(_RUNTIME_ADDRESS_FIELDS)
        },
        "approved_runtime_case_id": case_id,
        "approved_png_sha256": require_sha256(
            value["approved_png_sha256"], "Approved PNG"
        ),
    }


def _copy(value: Any) -> Any:
    return json.loads(_canonical(value))


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(
            value, ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
    except (OverflowError, TypeError, UnicodeError, ValueError) as exc:
        raise Spine42V3SetupRegressionManifestError(
            "Setup regression request is not finite JSON"
        ) from exc


__all__ = [
    "FORMAT", "FORMAT_VERSION", "HASH_DOMAIN", "MAX_REQUEST_BYTES",
    "MAX_SAMPLES", "Spine42V3SetupRegressionManifestError",
    "canonical_request_bytes", "parse_spine42_v3_setup_regression_request",
    "require_spine42_v3_setup_regression_request",
    "setup_regression_request_sha256",
]
