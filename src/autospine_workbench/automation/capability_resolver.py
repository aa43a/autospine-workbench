"""Capabilities of the setup-region preview operation, with no release grant."""
from __future__ import annotations

from copy import deepcopy
import re

from .pipeline_profile import build_pipeline_profile
from .project_snapshot import ProjectSnapshot
from ..region_rig_contract import RegionRigContractError, review_issues

SCHEMA = "autospine.project-capabilities/v1"
REASONS = (
    "project_review_required", "spine_preview_review_required",
    "region_geometry_unsupported", "certification_exact_entry_required",
    "operation_not_supported", "preview_has_no_release_authority",
)
_FLAGS = (
    "can_build_region_rig", "can_build_mesh_rig", "can_apply_motion",
    "can_export_spine", "can_build_spine_preview",
)
_ADDRESSES = (
    "resolved_project_sha256", "layer_manifest_sha256", "input_identity_sha256",
)


class CapabilityError(ValueError):
    def __init__(self, reason_code="invalid_project_capabilities"):
        self.reason_code = reason_code
        super().__init__(reason_code)


def _item(kind, identifier, reason):
    return {"type": kind, "id": identifier, "reason_code": reason}


def resolve_capabilities(
    snapshot: ProjectSnapshot, profile: str = "production_review",
) -> dict:
    """Do not infer capabilities of mesh, motion or release from a region rig."""
    build_pipeline_profile(profile)
    blocking, warnings = [], [
        _item("operation", "mesh", "operation_not_supported"),
        _item("operation", "motion", "operation_not_supported"),
        _item("operation", "release", "preview_has_no_release_authority"),
    ]
    try:
        needs_review = bool(review_issues(snapshot.manifest, snapshot.resolved))
    except RegionRigContractError:
        needs_review = True
    compilable = snapshot.region_compilation is not None
    if not compilable:
        blocking.append(_item("geometry", "region-rig", "region_geometry_unsupported"))
    if profile == "certification_exact":
        blocking.append(_item("profile", profile, "certification_exact_entry_required"))
    elif needs_review:
        item = _item("review", "project", "project_review_required")
        (warnings if profile == "draft_auto" else blocking).append(item)
        blocking.append(_item("review", "spine-preview", "spine_preview_review_required"))
    region = compilable and profile != "certification_exact" and (
        profile == "draft_auto" or not needs_review
    )
    return validate_project_capabilities({
        "schema": SCHEMA, "project_id": snapshot.project_id, "profile": profile,
        "operation": "setup_region_preview", "authority": "none",
        "source_addresses": deepcopy(snapshot.source_addresses),
        "can_build_region_rig": region,
        "can_build_mesh_rig": False, "can_apply_motion": False,
        "can_export_spine": False,
        "can_build_spine_preview": region and not needs_review,
        "blocking_items": blocking, "warning_items": warnings,
    })


def validate_project_capabilities(document: object) -> dict:
    """Strict public contract; reject invented authorities and local paths."""
    if not isinstance(document, dict) or set(document) != {
        "schema", "project_id", "profile", "operation", "authority",
        "source_addresses", "blocking_items", "warning_items", *_FLAGS,
    }:
        raise CapabilityError()
    if document["schema"] != SCHEMA or document["operation"] != "setup_region_preview" \
            or document["authority"] != "none":
        raise CapabilityError()
    identifier = document["project_id"]
    if not isinstance(identifier, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", identifier,
    ):
        raise CapabilityError()
    build_pipeline_profile(document["profile"])
    addresses = document["source_addresses"]
    if not isinstance(addresses, dict) or set(addresses) != set(_ADDRESSES) or any(
        not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value)
        for value in addresses.values()
    ):
        raise CapabilityError()
    if any(type(document[name]) is not bool for name in _FLAGS) or any(
        document[name] for name in ("can_build_mesh_rig", "can_apply_motion", "can_export_spine")
    ):
        raise CapabilityError()
    if document["can_build_spine_preview"] and not document["can_build_region_rig"]:
        raise CapabilityError()
    if document["profile"] == "certification_exact" and document["can_build_region_rig"]:
        raise CapabilityError()
    for key in ("blocking_items", "warning_items"):
        if not isinstance(document[key], list):
            raise CapabilityError()
        for item in document[key]:
            if not isinstance(item, dict) or set(item) != {"type", "id", "reason_code"}:
                raise CapabilityError()
            if item["type"] not in ("operation", "geometry", "profile", "review") \
                    or item["reason_code"] not in REASONS:
                raise CapabilityError()
            if not isinstance(item["id"], str) or not re.fullmatch(
                r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", item["id"],
            ):
                raise CapabilityError()
    if document["can_build_spine_preview"] and document["blocking_items"]:
        raise CapabilityError()
    return deepcopy(document)
