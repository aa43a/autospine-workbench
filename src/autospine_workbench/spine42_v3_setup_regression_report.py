"""Canonical self-hashed report for the P10.7c setup regression gate."""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
from typing import Any

from .manifest_artifacts import LayerManifestError
from .spine42_runtime_contract import (
    DEFAULT_BACKGROUND,
    DEFAULT_DPR,
    DEFAULT_VIEWPORT,
    RUNTIME_NPM_INTEGRITY,
)
from .spine42_contract import SPINE_RUNTIME_PACKAGE, SPINE_RUNTIME_VERSION
from .spine42_v3_setup_regression_manifest import (
    require_spine42_v3_setup_regression_request,
    setup_regression_request_sha256,
)
from .spine42_v3_setup_regression_profile import COMPARISON_PROFILE_SHA256
from .spine42_v3_setup_regression_sample import (
    Spine42V3SetupRegressionSampleError,
    require_setup_regression_sample,
)


FORMAT = "autospine-spine42-v3-setup-regression-report"
FORMAT_VERSION = 1
HASH_DOMAIN = "autospine-spine42-v3-setup-regression-report/v1"
_ROOT_FIELDS = {
    "format", "format_version", "request_sha256",
    "approved_p6_export_contract_sha256",
    "approved_runtime_golden_sha256", "comparison_profile_sha256",
    "runtime", "capture", "samples",
    "summary", "semantics", "authority", "status", "release_gate",
    "setup_regression_report_sha256",
}
SEMANTICS = {
    "scope": "bounded-setup-frame-only",
    "current_head_discovery": False,
    "official_runtime_execution": False,
    "approved_golden_selection": "explicit-case-and-exact-source-binding",
    "p6_setup_raster_comparison_included": True,
    "human_review_substitution": False,
    "continuous_time_safety_claimed": False,
    "release_authority": False,
}
AUTHORITY = {
    "state_mutation": False,
    "approved_golden_mutation": False,
    "human_decision": False,
    "publish": False,
    "release": False,
}
_BASE_RELEASE_REASONS = [
    "bounded_setup_frame_only",
    "continuous_runtime_raster_safety_unproven",
    "publish_authority_not_granted",
    "release_authority_not_granted",
]


class Spine42V3SetupRegressionReportError(ValueError):
    """Raised when a setup regression report can be forged or is inconsistent."""


def build_spine42_v3_setup_regression_report(
    request: Mapping[str, Any],
    samples: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build and immediately validate a path-free deterministic report."""

    request = require_spine42_v3_setup_regression_request(request)
    if type(samples) is not list or len(samples) != len(request["samples"]):
        raise Spine42V3SetupRegressionReportError(
            "Setup regression report sample count is invalid"
        )
    samples = [
        require_setup_regression_sample(row, expected)
        for row, expected in zip(samples, request["samples"], strict=True)
    ]
    passed = sum(row["status"] == "passed" for row in samples)
    rejected = len(samples) - passed
    status = "passed" if rejected == 0 else "rejected"
    reasons = list(_BASE_RELEASE_REASONS)
    if rejected:
        reasons.insert(0, "p6_setup_regression_rejected")
    report = {
        "format": FORMAT,
        "format_version": FORMAT_VERSION,
        "request_sha256": setup_regression_request_sha256(request),
        "approved_p6_export_contract_sha256":
            request["approved_p6_export_contract_sha256"],
        "approved_runtime_golden_sha256":
            request["approved_runtime_golden_sha256"],
        "comparison_profile_sha256": COMPARISON_PROFILE_SHA256,
        "runtime": {
            "package": SPINE_RUNTIME_PACKAGE,
            "version": SPINE_RUNTIME_VERSION,
            "npm_integrity": RUNTIME_NPM_INTEGRITY,
        },
        "capture": {
            "viewport": {"width": DEFAULT_VIEWPORT[0], "height": DEFAULT_VIEWPORT[1]},
            "device_pixel_ratio": DEFAULT_DPR,
            "background": DEFAULT_BACKGROUND,
        },
        "samples": samples,
        "summary": {
            "sample_count": len(samples),
            "passed_count": passed,
            "rejected_count": rejected,
        },
        "semantics": _copy(SEMANTICS),
        "authority": _copy(AUTHORITY),
        "status": status,
        "release_gate": {"status": "blocked", "reason_codes": reasons},
    }
    report["setup_regression_report_sha256"] = \
        setup_regression_report_sha256(report)
    return require_spine42_v3_setup_regression_report(report, request)


def require_spine42_v3_setup_regression_report(
    value: Mapping[str, Any],
    request: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate all derived fields and bind every sample to its request row."""

    try:
        request = require_spine42_v3_setup_regression_request(request)
        if type(value) is not dict or set(value) != _ROOT_FIELDS \
                or value.get("format") != FORMAT \
                or type(value.get("format_version")) is not int \
                or value.get("format_version") != FORMAT_VERSION \
                or value.get("request_sha256") != \
                    setup_regression_request_sha256(request) \
                or value.get("approved_p6_export_contract_sha256") != \
                    request["approved_p6_export_contract_sha256"] \
                or value.get("approved_runtime_golden_sha256") != \
                    request["approved_runtime_golden_sha256"] \
                or value.get("comparison_profile_sha256") != \
                    request["comparison_profile_sha256"]:
            raise Spine42V3SetupRegressionReportError(
                "Setup regression report identity is invalid"
            )
        _fixed_root(value)
        rows = value.get("samples")
        if type(rows) is not list or len(rows) != len(request["samples"]):
            raise Spine42V3SetupRegressionReportError(
                "Setup regression report sample count is invalid"
            )
        normalized = [
            require_setup_regression_sample(row, expected)
            for row, expected in zip(rows, request["samples"], strict=True)
        ]
        passed = sum(row["status"] == "passed" for row in normalized)
        rejected = len(normalized) - passed
        expected_status = "passed" if not rejected else "rejected"
        expected_reasons = list(_BASE_RELEASE_REASONS)
        if rejected:
            expected_reasons.insert(0, "p6_setup_regression_rejected")
        if not _same(value.get("summary"), {
            "sample_count": len(normalized), "passed_count": passed,
            "rejected_count": rejected,
        }) or value.get("status") != expected_status \
                or not _same(value.get("release_gate"), {
                    "status": "blocked", "reason_codes": expected_reasons,
                }) or value.get("setup_regression_report_sha256") != \
                    setup_regression_report_sha256(value):
            raise Spine42V3SetupRegressionReportError(
                "Setup regression report derived fields are invalid"
            )
        return _copy(value)
    except Spine42V3SetupRegressionReportError:
        raise
    except (
        LayerManifestError, KeyError, OverflowError,
        Spine42V3SetupRegressionSampleError, TypeError,
        UnicodeError, ValueError,
    ) as exc:
        raise Spine42V3SetupRegressionReportError(
            "Setup regression report validation failed"
        ) from exc


def _fixed_root(value) -> None:
    runtime = value.get("runtime")
    capture = value.get("capture")
    expected_runtime = {
        "package": SPINE_RUNTIME_PACKAGE, "version": SPINE_RUNTIME_VERSION,
        "npm_integrity": RUNTIME_NPM_INTEGRITY,
    }
    expected_capture = {
        "viewport": {"width": DEFAULT_VIEWPORT[0], "height": DEFAULT_VIEWPORT[1]},
        "device_pixel_ratio": DEFAULT_DPR, "background": DEFAULT_BACKGROUND,
    }
    if not _same(runtime, expected_runtime) \
            or not _same(capture, expected_capture) \
            or not _same(value.get("semantics"), SEMANTICS) \
            or not _same(value.get("authority"), AUTHORITY):
        raise Spine42V3SetupRegressionReportError(
            "Setup regression report fixed semantics are invalid"
        )


def setup_regression_report_sha256(value):
    """Return the content identity; this is not evidence authenticity."""

    body = _copy(value)
    body.pop("setup_regression_report_sha256", None)
    return hashlib.sha256(_canonical({"domain": HASH_DOMAIN, "report": body})).hexdigest()


def _same(actual, expected) -> bool:
    return _canonical(actual) == _canonical(expected)


def _copy(value):
    return json.loads(_canonical(value))


def _canonical(value):
    try:
        return json.dumps(value, ensure_ascii=False, allow_nan=False,
                          sort_keys=True, separators=(",", ":")).encode("utf-8")
    except (OverflowError, TypeError, UnicodeError, ValueError) as exc:
        raise Spine42V3SetupRegressionReportError(
            "Setup regression report is not finite JSON"
        ) from exc


__all__ = [
    "AUTHORITY", "FORMAT", "FORMAT_VERSION", "HASH_DOMAIN", "SEMANTICS",
    "Spine42V3SetupRegressionReportError",
    "build_spine42_v3_setup_regression_report",
    "require_spine42_v3_setup_regression_report",
    "setup_regression_report_sha256",
]
