"""Deterministic reports binding P4 IK probes to immutable target profiles."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import json
import math
from typing import Any

from .ik_probe_cases import (
    CASE_ORDER,
    FAR_RADIUS_MULTIPLIER,
    GEOMETRY_TOLERANCE_PX,
    NEAR_RADIUS_MULTIPLIER,
    REACHABLE_RADIUS_FRACTION,
    ROTATION_TOLERANCE_DEG,
    probe_handle,
)
from .ik_target_profile import SOURCE_IDENTITY_FIELDS
from .ik_target_profile_validation import (
    IkTargetProfileValidationError,
    require_ik_target_profile,
)
from .resolved_project import canonical_sha256


PROBER_ID = "ik-target-prober"
PROBER_VERSION = "1.0.0"
PROBE_PROFILE = "two-bone-analytic-target-probes-v1"


class IkProbeReportError(ValueError):
    """Raised when P4 numerical evidence cannot be reproduced safely."""


@dataclass(frozen=True, slots=True)
class IkProbeReport:
    """Frozen canonical report whose document accessor is isolated."""

    _document_json: str

    @property
    def document(self) -> dict[str, Any]:
        return json.loads(self._document_json)

    def to_json(self) -> str:
        return self._document_json


def probe_config() -> dict[str, Any]:
    """Return the exact current numerical probe configuration."""

    return {
        "profile": PROBE_PROFILE,
        "case_order": list(CASE_ORDER),
        "reachable_radius_fraction": REACHABLE_RADIUS_FRACTION,
        "far_radius_multiplier": FAR_RADIUS_MULTIPLIER,
        "near_radius_multiplier": NEAR_RADIUS_MULTIPLIER,
        "geometry_tolerance_px": GEOMETRY_TOLERANCE_PX,
        "rotation_tolerance_deg": ROTATION_TOLERANCE_DEG,
        "reach_scope": "kinematic-annulus-only",
        "mesh_visual_safety": "not-evaluated",
    }


def build_ik_probe_report(profile: Mapping[str, Any]) -> IkProbeReport:
    """Probe every canonical handle without mutating its setup or base RigIR."""

    try:
        require_ik_target_profile(profile)
        source = _mapping(profile.get("source"), "IK target profile source")
        handles = _sequence(profile.get("handles"), "IK target profile handles")
        entries = [probe_handle(_mapping(item, "IK target handle")) for item in handles]
        evaluated = sum(
            case["applicability"] == "evaluated"
            for entry in entries
            for case in entry["cases"]
        )
        not_applicable = sum(
            case["applicability"] == "not_applicable"
            for entry in entries
            for case in entry["cases"]
        )
        status = "rejected" if any(
            entry["gate"]["status"] == "rejected" for entry in entries
        ) else "passed"
        document = {
            "format": "autospine-ik-target-probes",
            "format_version": 1,
            "project_id": profile["project_id"],
            "source": {
                **{field: source[field] for field in SOURCE_IDENTITY_FIELDS},
                "profile_sha256": canonical_sha256(profile),
            },
            "prober": {
                "id": PROBER_ID,
                "version": PROBER_VERSION,
                "config": probe_config(),
            },
            "status": status,
            "summary": {
                "handle_count": len(entries),
                "evaluated_case_count": evaluated,
                "not_applicable_case_count": not_applicable,
            },
            "handles": entries,
        }
        _require_finite_tree(document)
        return IkProbeReport(_encode(document))
    except IkProbeReportError:
        raise
    except (
        IkTargetProfileValidationError,
        KeyError,
        OverflowError,
        TypeError,
        ValueError,
    ) as exc:
        raise IkProbeReportError(f"IK target probe report failed: {exc}") from exc


def require_ik_probe_report(
    document: Mapping[str, Any], *, profile: Mapping[str, Any]
) -> None:
    """Re-run every case and require exact canonical evidence and a passed gate."""

    if not isinstance(document, Mapping):
        raise IkProbeReportError("IK target probe report must be an object")
    expected = build_ik_probe_report(profile).document
    try:
        matches = canonical_sha256(document) == canonical_sha256(expected)
    except (TypeError, ValueError) as exc:
        raise IkProbeReportError(
            "IK target probe report is not canonical JSON"
        ) from exc
    if not matches:
        raise IkProbeReportError(
            "IK target probe report differs from recomputed numerical evidence"
        )
    if document.get("status") != "passed":
        raise IkProbeReportError("IK target probe numerical gate did not pass")


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise IkProbeReportError(f"{label} must be an object")
    return value


def _sequence(value: Any, label: str) -> list[Any]:
    if not isinstance(value, Sequence) or isinstance(
        value, (str, bytes, bytearray)
    ):
        raise IkProbeReportError(f"{label} must be an array")
    return list(value)


def _encode(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _require_finite_tree(value: Any) -> None:
    if isinstance(value, Mapping):
        for item in value.values():
            _require_finite_tree(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _require_finite_tree(item)
    elif isinstance(value, float) and not math.isfinite(value):
        raise IkProbeReportError(
            "IK target probe report contains a non-finite number"
        )
