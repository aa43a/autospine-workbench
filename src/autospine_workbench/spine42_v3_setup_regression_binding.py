"""Exact evidence replay boundary for P10.7c reports."""

from __future__ import annotations

import json

from .spine42_v3_setup_regression_comparison import (
    Spine42V3SetupRegressionError,
    compare_spine42_v3_setup_sample,
)
from .spine42_v3_setup_regression_manifest import (
    Spine42V3SetupRegressionManifestError,
    require_spine42_v3_setup_regression_request,
)
from .spine42_v3_setup_regression_report import (
    Spine42V3SetupRegressionReportError,
    build_spine42_v3_setup_regression_report,
    require_spine42_v3_setup_regression_report,
)


class Spine42V3SetupRegressionBindingError(ValueError):
    """Raised when a report differs from independently replayed evidence."""


def build_bound_spine42_v3_setup_regression_report(
    request, p6_approval, runtime_golden, approved_pngs, exact_sources,
):
    """Replay exact evidence and build the sole accepted report body."""

    try:
        request = require_spine42_v3_setup_regression_request(request)
        samples = _replay(
            request, p6_approval, runtime_golden,
            approved_pngs, exact_sources,
        )
        return build_spine42_v3_setup_regression_report(request, samples)
    except Spine42V3SetupRegressionBindingError:
        raise
    except _FAILURES as exc:
        raise Spine42V3SetupRegressionBindingError(
            "Setup regression report build failed"
        ) from exc


def require_spine42_v3_setup_regression_report_binding(
    report, request, p6_approval, runtime_golden,
    approved_pngs, exact_sources,
):
    """Independently replay exact sources before accepting report samples."""

    try:
        request = require_spine42_v3_setup_regression_request(request)
        report = require_spine42_v3_setup_regression_report(report, request)
        expected = _replay(
            request, p6_approval, runtime_golden,
            approved_pngs, exact_sources,
        )
        if _canonical(report["samples"]) != _canonical(expected):
            raise Spine42V3SetupRegressionBindingError(
                "Setup regression report differs from exact evidence replay"
            )
        return report
    except Spine42V3SetupRegressionBindingError:
        raise
    except _FAILURES as exc:
        raise Spine42V3SetupRegressionBindingError(
            "Setup regression report binding failed"
        ) from exc


def _replay(request, p6_approval, runtime_golden, approved_pngs, exact_sources):
    cases = [row["approved_runtime_case_id"] for row in request["samples"]]
    if type(approved_pngs) is not dict or set(approved_pngs) != set(cases) \
            or type(exact_sources) is not list \
            or len(exact_sources) != len(request["samples"]):
        raise Spine42V3SetupRegressionBindingError(
            "Setup regression replay inputs are incomplete"
        )
    result = []
    for sample, sources in zip(request["samples"], exact_sources, strict=True):
        if type(sources) is not tuple or len(sources) != 3:
            raise Spine42V3SetupRegressionBindingError(
                "Setup regression exact source tuple is invalid"
            )
        result.append(compare_spine42_v3_setup_sample(
            sample, p6_approval, runtime_golden,
            approved_pngs[sample["approved_runtime_case_id"]], *sources,
        ))
    return result


def _canonical(value) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")


_FAILURES = (
    KeyError, OverflowError, Spine42V3SetupRegressionError,
    Spine42V3SetupRegressionManifestError,
    Spine42V3SetupRegressionReportError, TypeError, UnicodeError, ValueError,
)


__all__ = [
    "Spine42V3SetupRegressionBindingError",
    "build_bound_spine42_v3_setup_regression_report",
    "require_spine42_v3_setup_regression_report_binding",
]
