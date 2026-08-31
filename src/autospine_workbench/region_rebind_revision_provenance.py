"""Internal immutable provenance stored with one override history revision."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
import json
import re
from typing import Any

from .region_rebind_profile import (
    MAX_MOTION_SAMPLES,
    region_rebind_analyzer_profile_sha256,
)
from .resolved_project import canonical_sha256


FORMAT = "autospine-region-rebind-revision-provenance"
FORMAT_VERSION = 1
INTENT = "region-rebind-adoption-v1"
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_TOP = {
    "format", "format_version", "intent", "project_id", "revision",
    "package_id", "candidate_sha256", "layer_id", "from_bone_id",
    "to_bone_id", "source", "current_chain", "p10_head",
}
_SOURCE = {
    "rig_sha256", "motion_sha256", "motion_samples_sha256",
    "motion_sample_count", "attachment_id", "slot_id", "current_bone_id",
    "candidate_bone_ids_sha256", "analyzer_profile_sha256",
}
_HEAD = {
    "current_revision", "head_decision_sha256", "action", "probe_status",
}


class RegionRebindRevisionProvenanceError(ValueError):
    """Raised when trusted revision provenance is malformed or rebound."""


def build_region_rebind_revision_provenance(
    *, package_id: str, candidate_sha256: str, project_id: str,
    revision: int, layer_id: str, from_bone_id: str, to_bone_id: str,
    source: Mapping[str, Any], resolved_project_sha256: str,
    layer_manifest_sha256: str, p10_head: Mapping[str, Any],
) -> dict[str, Any]:
    """Build and immediately validate one path-free revision receipt."""

    document = {
        "format": FORMAT,
        "format_version": FORMAT_VERSION,
        "intent": INTENT,
        "project_id": project_id,
        "revision": revision,
        "package_id": package_id,
        "candidate_sha256": candidate_sha256,
        "layer_id": layer_id,
        "from_bone_id": from_bone_id,
        "to_bone_id": to_bone_id,
        "source": deepcopy(dict(source)),
        "current_chain": {
            "resolved_project_sha256": resolved_project_sha256,
            "layer_manifest_sha256": layer_manifest_sha256,
        },
        "p10_head": deepcopy(dict(p10_head)),
    }
    return normalize_region_rebind_revision_provenance(
        document, project_id=project_id, revision=revision,
    )


def normalize_region_rebind_revision_provenance(
    value: Any, *, project_id: str, revision: int,
) -> dict[str, Any]:
    """Validate exact identities and return a JSON-detached canonical value."""

    root = _exact_object(value, _TOP, "revision provenance")
    if root.get("format") != FORMAT \
            or root.get("format_version") != FORMAT_VERSION \
            or root.get("intent") != INTENT:
        raise RegionRebindRevisionProvenanceError(
            "Revision provenance contract is invalid"
        )
    if root.get("project_id") != project_id or root.get("revision") != revision:
        raise RegionRebindRevisionProvenanceError(
            "Revision provenance address differs"
        )
    _identifier(project_id, "project_id")
    if type(revision) is not int or revision < 1:
        raise RegionRebindRevisionProvenanceError("revision is invalid")
    for field in ("layer_id", "from_bone_id", "to_bone_id"):
        _identifier(root.get(field), field)
    for field in ("package_id", "candidate_sha256"):
        _digest(root.get(field), field)
    _source(root.get("source"), root["layer_id"], root["from_bone_id"])
    chain = _exact_object(
        root.get("current_chain"),
        {"resolved_project_sha256", "layer_manifest_sha256"},
        "current chain",
    )
    for field in chain:
        _digest(chain[field], field)
    _head(root.get("p10_head"))
    try:
        raw = json.dumps(
            root, ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
        return json.loads(raw.decode("utf-8"))
    except (OverflowError, TypeError, ValueError) as exc:
        raise RegionRebindRevisionProvenanceError(
            "Revision provenance is not canonical JSON"
        ) from exc


def region_rebind_revision_provenance_sha256(value: Mapping[str, Any]) -> str:
    """Return the canonical identity of an already-normalized receipt."""

    return canonical_sha256(value)


def region_rebind_adoption_receipt(
    *, package_id: str, candidate_sha256: str,
    request: Mapping[str, Any], provenance: Mapping[str, Any],
    saved: Mapping[str, Any],
) -> dict[str, Any]:
    """Project one path-free receipt from the committed revision."""

    return {
        "format": "autospine-region-rebind-adoption-receipt",
        "format_version": 1,
        "status": "adopted",
        "project_id": request["project_id"],
        "revision": saved["revision"],
        "package_id": package_id,
        "candidate_sha256": candidate_sha256,
        "layer_id": request["layer_id"],
        "from_bone_id": request["from_bone_id"],
        "to_bone_id": request["to_bone_id"],
        "provenance_sha256": region_rebind_revision_provenance_sha256(
            provenance
        ),
        "provenance": deepcopy(dict(provenance)),
        "overrides": deepcopy(dict(saved)),
    }


def _source(value: Any, layer_id: str, from_bone_id: str) -> None:
    source = _exact_object(value, _SOURCE, "candidate source")
    for field in (
        "rig_sha256", "motion_sha256", "motion_samples_sha256",
        "candidate_bone_ids_sha256", "analyzer_profile_sha256",
    ):
        _digest(source.get(field), field)
    for field in ("attachment_id", "slot_id", "current_bone_id"):
        _identifier(source.get(field), field)
    count = source.get("motion_sample_count")
    if type(count) is not int or not 2 <= count <= MAX_MOTION_SAMPLES:
        raise RegionRebindRevisionProvenanceError(
            "motion_sample_count is invalid"
        )
    if source["analyzer_profile_sha256"] \
            != region_rebind_analyzer_profile_sha256():
        raise RegionRebindRevisionProvenanceError(
            "Candidate analyzer profile differs"
        )
    if source["attachment_id"] != layer_id \
            or source["current_bone_id"] != from_bone_id:
        raise RegionRebindRevisionProvenanceError(
            "Candidate source binding differs"
        )


def _head(value: Any) -> None:
    head = _exact_object(value, _HEAD, "P10 head")
    revision = head.get("current_revision")
    if type(revision) is not int or revision < 1 \
            or not _SHA.fullmatch(str(head.get("head_decision_sha256", ""))) \
            or head.get("action") != "adjust" \
            or head.get("probe_status") != "pending_probe":
        raise RegionRebindRevisionProvenanceError("P10 head is not adoptable")


def _exact_object(value: Any, fields: set[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise RegionRebindRevisionProvenanceError(f"{label} fields are invalid")
    return value


def _identifier(value: Any, label: str) -> None:
    if not isinstance(value, str) or not _SAFE_ID.fullmatch(value):
        raise RegionRebindRevisionProvenanceError(f"{label} is invalid")


def _digest(value: Any, label: str) -> None:
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        raise RegionRebindRevisionProvenanceError(f"{label} is invalid")
