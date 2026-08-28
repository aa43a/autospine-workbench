"""Read-only exact-address readiness audit for the P10.7b real gate."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .spine42_v3_readiness_manifest import (
    require_spine42_v3_readiness_request,
    spine42_v3_readiness_request_sha256,
)
from .spine42_v3_readiness_binding import (
    require_spine42_v3_readiness_report_binding,
)
from .spine42_v3_readiness_stages import audit_spine42_v3_sample
from .spine42_v3_readiness_validation import (
    require_spine42_v3_readiness_report,
)
from .spine42_v3_raster_review_values import domain_sha256


FORMAT = "autospine-spine42-v3-readiness-report"
FORMAT_VERSION = 1
REPORT_DOMAIN = "autospine-spine42-v3-readiness-report/v1"


class Spine42V3ReadinessError(RuntimeError):
    """Raised when a readiness request cannot be audited safely."""


def audit_spine42_v3_readiness(
    request: Mapping[str, Any], state_root: Path,
) -> dict[str, Any]:
    """Audit declared addresses and known human gates without state writes."""

    try:
        request = require_spine42_v3_readiness_request(request)
        root = Path(state_root)
        samples = [
            audit_spine42_v3_sample(row, root)
            for row in request["samples"]
        ]
        ready = all(
            row["status"] == "ready_for_p6_setup_comparison"
            for row in samples
        )
        report = {
            "format": FORMAT,
            "format_version": FORMAT_VERSION,
            "request_sha256": spine42_v3_readiness_request_sha256(request),
            "samples": samples,
            "summary": _summary(samples),
            "semantics": {
                "scope": "exact-address-read-only-preflight",
                "current_head_discovery": False,
                "external_stage_execution": False,
                "pure_replay_compilation": True,
                "human_review_substitution": False,
                "p6_setup_raster_comparison_included": False,
                "release_authority": False,
            },
            "authority": {
                "state_mutation": False,
                "latest_selection": False,
                "pipeline_execution": False,
                "human_decision": False,
                "publish": False,
                "release": False,
            },
            "status": (
                "ready_for_p6_setup_comparison" if ready
                else "blocked_prerequisites_or_review"
            ),
            "release_gate": {
                "status": "blocked",
                "reason_codes": [
                    "bounded_preflight_not_release_authority",
                    "p6_setup_golden_comparison_missing",
                ],
            },
        }
        report["readiness_report_sha256"] = domain_sha256(
            REPORT_DOMAIN, report
        )
        require_spine42_v3_readiness_report(report)
        require_spine42_v3_readiness_report_binding(report, request)
        return report
    except Spine42V3ReadinessError:
        raise
    except (KeyError, OSError, RuntimeError, TypeError, ValueError) as exc:
        raise Spine42V3ReadinessError(
            "Spine 4.2 v3 readiness audit failed"
        ) from exc


def _summary(samples: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {
        name: 0 for name in (
            "verified", "prerequisite_missing", "review_blocked",
            "metrics_rejected", "source_mismatch",
        )
    }
    for sample in samples:
        for checkpoint in sample["checkpoints"]:
            counts[checkpoint["status"]] += 1
    return {
        "sample_count": len(samples),
        "ready_for_p6_setup_comparison_count": sum(
            row["status"] == "ready_for_p6_setup_comparison"
            for row in samples
        ),
        "blocked_sample_count": sum(row["status"] == "blocked" for row in samples),
        "checkpoint_status_counts": counts,
    }


__all__ = [
    "Spine42V3ReadinessError", "audit_spine42_v3_readiness",
]
