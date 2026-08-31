"""Live project relationship checks for a reviewed region rebind."""

from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any


_SHA = re.compile(r"^[0-9a-f]{64}$")


class RegionRebindAdoptionEvidenceError(ValueError):
    """Raised when candidate topology differs from the live project."""


class RegionRebindLayerUnavailable(RegionRebindAdoptionEvidenceError):
    """The selected layer or target bone is absent from the live project."""


class RegionRebindLayerBindingChanged(RegionRebindAdoptionEvidenceError):
    """The effective source binding no longer matches the recommendation."""


def require_idle_candidate_identity(
    detail: Mapping[str, Any], report: Mapping[str, Any],
) -> str:
    """Bind the transaction lock to the exact reviewed P10.0 candidate."""

    value = detail.get("candidate_sha256")
    try:
        expected = report["source"]["idle_behavior_candidates_sha256"]
    except (KeyError, TypeError) as exc:
        raise RegionRebindAdoptionEvidenceError(
            "Idle behavior candidate identity is unavailable"
        ) from exc
    if not isinstance(value, str) or not _SHA.fullmatch(value) \
            or value != expected:
        raise RegionRebindAdoptionEvidenceError(
            "Idle behavior candidate identity differs"
        )
    return value


def require_current_region_binding(
    project: Mapping[str, Any], request: Mapping[str, Any],
) -> None:
    """Require the live layer/from/to tuple before reading candidate evidence."""

    layers = project.get("resolved", {}).get("layers", [])
    matches = [row for row in layers if row.get("id") == request["layer_id"]]
    if len(matches) != 1:
        raise RegionRebindLayerUnavailable("Layer is unavailable")
    if matches[0].get("candidate_bone") != request["from_bone_id"]:
        raise RegionRebindLayerBindingChanged(
            "Current effective binding differs from candidate source"
        )
    bone_ids = {
        row.get("id") for row in project.get("skeleton", {}).get("bones", [])
    }
    if request["to_bone_id"] not in bone_ids:
        raise RegionRebindLayerUnavailable("Target bone is unavailable")


def require_live_region_rebind_relationship(
    project: Mapping[str, Any],
    document: Mapping[str, Any],
    request: Mapping[str, Any],
) -> None:
    """Require the recommended target to remain a one-hop live neighbor."""

    try:
        bones = {
            row.get("id"): row for row in project["skeleton"]["bones"]
        }
        selected = next((
            row for row in document["candidates"]
            if row["bone_id"] == request["to_bone_id"]
        ), None)
        source = request["from_bone_id"]
        target = request["to_bone_id"]
        if selected is None or source not in bones or target not in bones:
            raise RegionRebindAdoptionEvidenceError(
                "Recommended bone evidence is missing"
            )
        relation = selected["relationship"]
        source_parent = bones[source].get(
            "parent_id", bones[source].get("parent")
        )
        target_parent = bones[target].get(
            "parent_id", bones[target].get("parent")
        )
        if not (
            relation == "parent" and source_parent == target
            or relation == "child" and target_parent == source
        ):
            raise RegionRebindAdoptionEvidenceError(
                "Live bone relationship differs"
            )
    except RegionRebindAdoptionEvidenceError:
        raise
    except (AttributeError, KeyError, StopIteration, TypeError) as exc:
        raise RegionRebindAdoptionEvidenceError(
            "Live bone relationship is unavailable"
        ) from exc
