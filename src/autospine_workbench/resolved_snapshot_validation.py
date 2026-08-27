"""Public strict semantic validator for ``autospine.resolved-project/v1``."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .resolved_project import RESOLVED_SCHEMA_VERSION, canonical_sha256
from .resolved_snapshot_entities import ResolvedEntities, validate_entities
from .resolved_snapshot_primitives import (
    ResolvedSnapshotValidationError,
    exact_string_list,
    fail,
    integer,
    object_exact,
    safe_id,
    sha256,
)
from .resolved_snapshot_provenance import validate_provenance


RESOLVED_SNAPSHOT_SCHEMA_VERSION = RESOLVED_SCHEMA_VERSION
_TOP_FIELDS = {
    "schema_version", "project_id", "revision", "inputs", "canvas", "layers",
    "skeleton", "qa", "sha256",
}
_QA_FIELDS = {
    "status", "review_layer_ids", "unresolved_joint_ids", "rejected_joint_ids",
    "unobservable_joint_ids", "accepted_split_layer_ids",
    "unreviewed_split_layer_ids", "rejected_split_layer_ids",
    "stale_split_layer_ids",
}
_SPLIT_DISPOSITIONS = {"split", "split_left_right"}


def require_resolved_snapshot(
    document: Any,
    *,
    expected_project_id: str | None = None,
    expected_revision: int | None = None,
    expected_base_project_sha256: str | None = None,
    expected_override_sha256: str | None = None,
) -> None:
    """Validate a complete v1 snapshot without reading external artifacts.

    Optional expected identities let API and compiler boundaries bind the
    otherwise standalone document to trusted context. Candidate and split
    artifact replay remains the responsibility of their existing binders.
    """

    root = object_exact(document, required=_TOP_FIELDS, path="$")
    if root.get("schema_version") != RESOLVED_SNAPSHOT_SCHEMA_VERSION:
        fail("$.schema_version", "resolved snapshot version is unsupported", "version")
    project_id = safe_id(root.get("project_id"), "$.project_id")
    revision = integer(root.get("revision"), "$.revision")
    entities = validate_entities(
        root.get("canvas"), root.get("layers"), root.get("skeleton"),
        project_id=project_id,
    )
    inputs = validate_provenance(root.get("inputs"), entities, revision=revision)
    _qa(root.get("qa"), entities)
    digest = sha256(root.get("sha256"), "$.sha256")
    unhashed = dict(root)
    unhashed.pop("sha256")
    try:
        observed = canonical_sha256(unhashed)
    except (OverflowError, TypeError, UnicodeError, ValueError) as exc:
        raise ResolvedSnapshotValidationError(
            "$", "snapshot is not canonical JSON data", "canonical_json"
        ) from exc
    if digest != observed:
        fail("$.sha256", "does not match canonical snapshot content", "content_address")
    _expected_identity(
        project_id=project_id,
        revision=revision,
        inputs=inputs,
        expected_project_id=expected_project_id,
        expected_revision=expected_revision,
        expected_base_project_sha256=expected_base_project_sha256,
        expected_override_sha256=expected_override_sha256,
    )


def resolved_snapshot_sha256(document: Any, **expected: Any) -> str:
    """Return a snapshot's verified canonical digest."""

    require_resolved_snapshot(document, **expected)
    assert isinstance(document, Mapping)
    return str(document["sha256"])


def _qa(value: Any, entities: ResolvedEntities) -> None:
    qa = object_exact(value, required=_QA_FIELDS, path="$.qa")
    status = qa.get("status")
    if status not in {"ready", "needs_review"}:
        fail("$.qa.status", "QA status is unsupported", "enum")
    layer_ids = {str(layer["id"]) for layer in entities.layers}
    joint_ids = set(entities.joints)
    observed: dict[str, list[str]] = {}
    for field in _QA_FIELDS - {"status"}:
        path = f"$.qa.{field}"
        values = exact_string_list(qa.get(field), path, maximum=4096)
        known = layer_ids if "layer" in field else joint_ids
        unknown = [item for item in values if item not in known]
        if unknown:
            fail(path, f"references unknown id {unknown[0]}", "cross_reference")
        observed[field] = values

    review_layers = [
        str(layer["id"])
        for layer in entities.layers
        if layer.get("disposition") == "review"
        or (layer.get("empty") and layer.get("disposition") != "exclude")
    ]
    unresolved = [
        joint_id
        for joint_id, joint in entities.joints.items()
        if joint.get("review_state") == "candidate_rejected"
        or (
            joint.get("review_state") == "unreviewed"
            and (entities.requires_review or float(joint["model_confidence"]) < 0.5)
        )
    ]
    rejected = [
        joint_id for joint_id, joint in entities.joints.items()
        if joint.get("review_state") == "candidate_rejected"
    ]
    unobservable = [
        joint_id for joint_id, joint in entities.joints.items()
        if joint.get("review_state") == "unobservable"
    ]
    split_layers = {
        str(layer["id"]): layer
        for layer in entities.layers
        if layer.get("disposition") in _SPLIT_DISPOSITIONS
    }
    accepted: list[str] = []
    rejected_split: list[str] = []
    stale: list[str] = []
    for layer in entities.layers:
        layer_id = str(layer["id"])
        decision = layer.get("split_decision")
        if not isinstance(decision, Mapping):
            continue
        if decision.get("binding_status") != "current":
            stale.append(layer_id)
        elif decision.get("action") == "accept":
            accepted.append(layer_id)
        elif decision.get("action") == "reject":
            rejected_split.append(layer_id)
    accepted.sort()
    rejected_split.sort()
    stale.sort()
    classified = set(accepted) | set(rejected_split) | set(stale)
    unreviewed_split = sorted(set(split_layers) - classified)
    expected = {
        "review_layer_ids": review_layers,
        "unresolved_joint_ids": unresolved,
        "rejected_joint_ids": rejected,
        "unobservable_joint_ids": unobservable,
        "accepted_split_layer_ids": accepted,
        "unreviewed_split_layer_ids": unreviewed_split,
        "rejected_split_layer_ids": rejected_split,
        "stale_split_layer_ids": stale,
    }
    for field, items in expected.items():
        if observed[field] != items:
            fail(f"$.qa.{field}", "does not match resolved entity state", "derived")
    expected_status = (
        "ready"
        if not review_layers and not unresolved
        and not unreviewed_split and not rejected_split and not stale
        else "needs_review"
    )
    if status != expected_status:
        fail("$.qa.status", "does not match derived review state", "derived")


def require_resolved_snapshot_for_project(
    document: Any,
    project: Mapping[str, Any],
    overrides: Mapping[str, Any] | None = None,
) -> None:
    """Bind a snapshot to the exact base project and optional override state."""

    project_id = safe_id(project.get("id"), "project.id")
    base_payload = {
        "source": project.get("source"),
        "canvas": project.get("canvas"),
        "layers": project.get("layers"),
        "skeleton": project.get("skeleton"),
    }
    decision = overrides if overrides is not None else project.get("overrides")
    if not isinstance(decision, Mapping):
        raise ResolvedSnapshotValidationError(
            "project.overrides",
            "trusted override state is required",
            "required",
        )
    expected_revision = integer(
        decision.get("revision"), "project.overrides.revision"
    )
    expected_override_sha256: str | None = None
    try:
        base_sha256 = canonical_sha256(base_payload)
        expected_override_sha256 = canonical_sha256(decision)
    except (OverflowError, TypeError, UnicodeError, ValueError) as exc:
        raise ResolvedSnapshotValidationError(
            "project", "trusted project context is not canonical JSON data",
            "canonical_json",
        ) from exc
    require_resolved_snapshot(
        document,
        expected_project_id=project_id,
        expected_revision=expected_revision,
        expected_base_project_sha256=base_sha256,
        expected_override_sha256=expected_override_sha256,
    )


def _expected_identity(
    *,
    project_id: str,
    revision: int,
    inputs: Mapping[str, Any],
    expected_project_id: str | None,
    expected_revision: int | None,
    expected_base_project_sha256: str | None,
    expected_override_sha256: str | None,
) -> None:
    if expected_project_id is not None:
        safe_id(expected_project_id, "expected_project_id")
        if project_id != expected_project_id:
            fail("$.project_id", "does not match trusted project identity", "identity")
    if expected_revision is not None:
        integer(expected_revision, "expected_revision")
        if revision != expected_revision:
            fail("$.revision", "does not match trusted revision", "identity")
    for field, expected in (
        ("base_project_sha256", expected_base_project_sha256),
        ("override_sha256", expected_override_sha256),
    ):
        if expected is None:
            continue
        sha256(expected, f"expected_{field}")
        if inputs.get(field) != expected:
            fail(f"$.inputs.{field}", "does not match trusted identity", "identity")


__all__ = [
    "RESOLVED_SNAPSHOT_SCHEMA_VERSION",
    "ResolvedSnapshotValidationError",
    "require_resolved_snapshot",
    "require_resolved_snapshot_for_project",
    "resolved_snapshot_sha256",
]
