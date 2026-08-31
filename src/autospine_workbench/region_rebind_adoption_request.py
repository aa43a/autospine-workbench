"""Strict path-bound request normalization for region rebind adoption."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
import re
from typing import Any


_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_REQUEST_FIELDS = {
    "project_id", "layer_id", "from_bone_id", "to_bone_id",
    "candidate_sha256", "base_revision", "overrides",
}
_MUTABLE_OVERRIDE_FIELDS = {
    "schema_version", "joint_overrides", "joint_decisions",
    "split_decisions", "layer_overrides", "notes",
}
_OVERRIDE_METADATA_FIELDS = {"contract", "project_id", "revision"}


class RegionRebindAdoptionRequestError(ValueError):
    """Raised before any state mutation for an invalid adoption request."""


def require_region_rebind_adoption_request(
    package_id: str, candidate_sha256: str, payload: Any,
) -> dict[str, Any]:
    """Return one detached request bound to both immutable path identities."""

    _digest(package_id, "package_id")
    _digest(candidate_sha256, "candidate_sha256")
    root = _object(payload, "request")
    if set(root) != _REQUEST_FIELDS:
        raise RegionRebindAdoptionRequestError("Request fields are invalid")
    for field in ("project_id", "layer_id", "from_bone_id", "to_bone_id"):
        _identifier(root.get(field), field)
    if root.get("candidate_sha256") != candidate_sha256:
        raise RegionRebindAdoptionRequestError("Candidate address differs")
    base = root.get("base_revision")
    if type(base) is not int or base < 0:
        raise RegionRebindAdoptionRequestError("base_revision is invalid")
    overrides = _object(root.get("overrides"), "overrides")
    allowed = _MUTABLE_OVERRIDE_FIELDS | _OVERRIDE_METADATA_FIELDS
    required = _MUTABLE_OVERRIDE_FIELDS - {"schema_version"}
    if not set(overrides).issubset(allowed) or not required.issubset(overrides):
        raise RegionRebindAdoptionRequestError(
            "Override payload fields are invalid"
        )
    if overrides.get("project_id", root["project_id"]) != root["project_id"] \
            or overrides.get("revision", base) != base:
        raise RegionRebindAdoptionRequestError("Override metadata differs")
    result = deepcopy(dict(root))
    result["overrides"] = deepcopy(dict(overrides))
    return result


def region_rebind_override_payload(request: Mapping[str, Any]) -> dict[str, Any]:
    """Apply only the selected target bone; never modify user-authored notes."""

    supplied = _object(request.get("overrides"), "overrides")
    layer_overrides = deepcopy(supplied["layer_overrides"])
    layer_id = request["layer_id"]
    patch = _object(layer_overrides.get(layer_id, {}), "layer override")
    existing = patch.get("candidate_bone")
    permitted = {None, request["from_bone_id"], request["to_bone_id"]}
    if existing not in permitted:
        raise RegionRebindAdoptionRequestError(
            "Draft binding conflicts with adoption"
        )
    patch = deepcopy(dict(patch))
    patch["candidate_bone"] = request["to_bone_id"]
    layer_overrides[layer_id] = patch
    if not isinstance(supplied["notes"], str):
        raise RegionRebindAdoptionRequestError("Override notes are invalid")
    result = {
        "base_revision": request["base_revision"],
        "joint_overrides": deepcopy(supplied["joint_overrides"]),
        "joint_decisions": deepcopy(supplied["joint_decisions"]),
        "split_decisions": deepcopy(supplied["split_decisions"]),
        "layer_overrides": layer_overrides,
        "notes": supplied["notes"],
    }
    if "schema_version" in supplied:
        result["schema_version"] = supplied["schema_version"]
    return result


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise RegionRebindAdoptionRequestError(f"{label} must be an object")
    return value


def _identifier(value: Any, label: str) -> None:
    if not isinstance(value, str) or not _SAFE_ID.fullmatch(value):
        raise RegionRebindAdoptionRequestError(f"{label} is invalid")


def _digest(value: Any, label: str) -> None:
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        raise RegionRebindAdoptionRequestError(f"{label} is invalid")
