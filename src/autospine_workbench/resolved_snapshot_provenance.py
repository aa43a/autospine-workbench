"""Candidate, review, and split provenance checks for resolved snapshots."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .resolved_project import canonical_sha256
from .resolved_snapshot_entities import ResolvedEntities
from .resolved_snapshot_primitives import (
    array,
    fail,
    object_exact,
    point,
    safe_id,
    sha256,
    text,
    version,
)


_INPUT_REQUIRED = {"base_project_sha256", "override_sha256", "candidate_analyses"}
_ANALYSIS_FIELDS = {
    "provider", "provider_version", "input_sha256", "config_sha256", "run_sha256",
}
_CANDIDATE_FIELDS = {
    "action", "candidate_artifact_sha256", "candidate_id", "final_xy", "reason",
    "analysis",
}
_SPLIT_ACTIONS = {"accept", "reject"}
_SPLIT_DISPOSITIONS = {"split", "split_left_right"}


def validate_provenance(
    inputs_value: Any,
    entities: ResolvedEntities,
    *,
    revision: int,
) -> Mapping[str, Any]:
    inputs = object_exact(
        inputs_value,
        required=_INPUT_REQUIRED,
        optional={"analysis_sha256"},
        path="$.inputs",
    )
    sha256(inputs.get("base_project_sha256"), "$.inputs.base_project_sha256")
    sha256(inputs.get("override_sha256"), "$.inputs.override_sha256")
    if "analysis_sha256" in inputs:
        sha256(inputs["analysis_sha256"], "$.inputs.analysis_sha256")
    supplied = _candidate_analysis_inventory(inputs.get("candidate_analyses"))
    derived: dict[str, dict[str, str]] = {}
    for index, joint in enumerate(entities.joints.values()):
        _joint_review(joint, f"$.skeleton.joints[{index}]", entities, revision, derived)
    expected = [
        {"candidate_artifact_sha256": digest, **derived[digest]}
        for digest in sorted(derived)
    ]
    if supplied != expected:
        fail(
            "$.inputs.candidate_analyses",
            "must exactly match the joint decision artifact inventory",
            "provenance",
        )
    for index, layer in enumerate(entities.layers):
        _layer_review(layer, f"$.layers[{index}]", entities, revision)
    return inputs


def _candidate_analysis_inventory(value: Any) -> list[dict[str, str]]:
    items = array(value, "$.inputs.candidate_analyses")
    result: list[dict[str, str]] = []
    previous = ""
    for index, raw in enumerate(items):
        path = f"$.inputs.candidate_analyses[{index}]"
        item = object_exact(
            raw,
            required={"candidate_artifact_sha256", *_ANALYSIS_FIELDS},
            path=path,
        )
        digest = sha256(item.get("candidate_artifact_sha256"), f"{path}.candidate_artifact_sha256")
        if digest <= previous:
            fail(path, "candidate analyses must be unique and sorted by artifact SHA", "order")
        previous = digest
        analysis = _analysis(item, path)
        result.append({"candidate_artifact_sha256": digest, **analysis})
    return result


def _analysis(value: Mapping[str, Any], path: str) -> dict[str, str]:
    provider = safe_id(value.get("provider"), f"{path}.provider")
    provider_version = version(value.get("provider_version"), f"{path}.provider_version")
    input_sha = sha256(value.get("input_sha256"), f"{path}.input_sha256")
    config_sha = sha256(value.get("config_sha256"), f"{path}.config_sha256")
    run_sha = sha256(value.get("run_sha256"), f"{path}.run_sha256")
    expected = canonical_sha256(
        {
            "input_sha256": input_sha,
            "provider": provider,
            "provider_version": provider_version,
            "config_sha256": config_sha,
        }
    )
    if run_sha != expected:
        fail(f"{path}.run_sha256", "candidate run identity is inconsistent", "identity")
    return {
        "provider": provider,
        "provider_version": provider_version,
        "input_sha256": input_sha,
        "config_sha256": config_sha,
        "run_sha256": run_sha,
    }


def _joint_review(
    joint: Mapping[str, Any],
    path: str,
    entities: ResolvedEntities,
    revision: int,
    derived: dict[str, dict[str, str]],
) -> None:
    state = joint["review_state"]
    kind = joint.get("decision_kind")
    decision = joint.get("decision")
    decision_revision = joint.get("decision_revision")
    if state == "unreviewed":
        _forbid(joint, path, {
            "decision_kind", "decision_revision", "decision", "review_reason",
            "legacy_review_confidence",
        })
        return
    if decision_revision != revision:
        fail(f"{path}.decision_revision", "must equal snapshot revision", "revision")
    if state == "manual_adjusted" and kind == "manual_absolute":
        if decision is not None:
            fail(f"{path}.decision", "manual absolute review cannot embed a candidate decision", "conflict")
        return
    expected = {
        "candidate_accepted": ("accept", "candidate_accept"),
        "manual_adjusted": ("adjust", "candidate_adjust"),
        "candidate_rejected": ("reject", "candidate_reject"),
        "unobservable": ("unobservable", "candidate_unobservable"),
    }.get(state)
    if expected is None or kind != expected[1]:
        fail(f"{path}.decision_kind", "does not match review state", "state")
    if "review_reason" in joint or "legacy_review_confidence" in joint:
        fail(path, "candidate reviews cannot carry manual-override metadata", "conflict")
    if not isinstance(decision, Mapping):
        fail(f"{path}.decision", "candidate decision is required", "required")
    digest, analysis = _candidate_decision(
        decision, f"{path}.decision", entities, expected[0], joint
    )
    previous = derived.get(digest)
    if previous is not None and previous != analysis:
        fail(f"{path}.decision.analysis", "artifact analysis conflicts with another joint", "provenance")
    derived[digest] = analysis


def _candidate_decision(
    value: Mapping[str, Any],
    path: str,
    entities: ResolvedEntities,
    expected_action: str,
    joint: Mapping[str, Any],
) -> tuple[str, dict[str, str]]:
    decision = object_exact(value, required={"action", "candidate_artifact_sha256", "analysis"}, optional=_CANDIDATE_FIELDS - {"action", "candidate_artifact_sha256", "analysis"}, path=path)
    action = decision.get("action")
    if action != expected_action:
        fail(f"{path}.action", "does not match resolved review state", "state")
    digest = sha256(decision.get("candidate_artifact_sha256"), f"{path}.candidate_artifact_sha256")
    analysis_root = object_exact(decision.get("analysis"), required=_ANALYSIS_FIELDS, path=f"{path}.analysis")
    analysis = _analysis(analysis_root, f"{path}.analysis")
    candidate_id = decision.get("candidate_id")
    final_xy = decision.get("final_xy")
    reason = decision.get("reason")
    if action in {"accept", "adjust", "reject"}:
        safe_id(candidate_id, f"{path}.candidate_id")
    elif "candidate_id" in decision:
        fail(f"{path}.candidate_id", "is forbidden for unobservable", "forbidden")
    if action in {"accept", "adjust"}:
        final = point(final_xy, f"{path}.final_xy", entities.width, entities.height)
        if final != (float(joint["x"]), float(joint["y"])):
            fail(f"{path}.final_xy", "does not match resolved joint coordinates", "identity")
    elif "final_xy" in decision:
        fail(f"{path}.final_xy", f"is forbidden for {action}", "forbidden")
    if action in {"adjust", "reject", "unobservable"}:
        text(reason, f"{path}.reason", maximum=1000, nonblank=True)
    elif "reason" in decision:
        text(reason, f"{path}.reason", maximum=1000, nonblank=True)
    return digest, analysis


def _layer_review(
    layer: Mapping[str, Any], path: str, entities: ResolvedEntities, revision: int
) -> None:
    reviewed = set(layer["reviewed_fields"])
    if layer["review_state"] == "unreviewed":
        if reviewed:
            fail(f"{path}.reviewed_fields", "unreviewed layer cannot claim reviewed fields", "state")
        _forbid(layer, path, {"decision_revision", "candidate_bone", "notes", "split_spec", "split_spec_revision"})
    elif layer.get("decision_revision") != revision:
        fail(f"{path}.decision_revision", "must equal snapshot revision", "revision")
    for field in ("candidate_bone", "notes"):
        if (field in layer) != (field in reviewed):
            fail(f"{path}.{field}", "presence must match reviewed_fields", "provenance")
    if "split_spec" in layer:
        if layer.get("side") != "bilateral" or layer.get("disposition") not in _SPLIT_DISPOSITIONS:
            fail(f"{path}.split_spec", "requires a bilateral split disposition", "state")
        if layer.get("split_spec_revision") != revision:
            fail(f"{path}.split_spec_revision", "must equal snapshot revision", "revision")
        if "candidate_bone" in layer or "candidate_bone" in reviewed or "pivot_xy" in reviewed:
            fail(f"{path}.split_spec", "split authoring cannot claim a single pivot or bone", "conflict")
        _split_spec(layer["split_spec"], f"{path}.split_spec", entities)
    elif "split_spec_revision" in layer:
        fail(f"{path}.split_spec_revision", "requires split_spec", "orphan")
    if "split_decision" in layer:
        if layer.get("split_decision_revision") != revision:
            fail(f"{path}.split_decision_revision", "must equal snapshot revision", "revision")
        _split_decision(layer["split_decision"], f"{path}.split_decision", layer)
    elif "split_decision_revision" in layer:
        fail(f"{path}.split_decision_revision", "requires split_decision", "orphan")


def _split_spec(value: Any, path: str, entities: ResolvedEntities) -> None:
    root = object_exact(value, required={"parts"}, path=path)
    parts = object_exact(root.get("parts"), required={"left", "right"}, path=f"{path}.parts")
    for side in ("left", "right"):
        part_path = f"{path}.parts.{side}"
        part = object_exact(parts.get(side), required={"guide", "pivot", "candidate_bone"}, path=part_path)
        bone = safe_id(part.get("candidate_bone"), f"{part_path}.candidate_bone")
        if bone not in entities.bones or not bone.endswith(f".{side}"):
            fail(f"{part_path}.candidate_bone", "must reference a same-side skeleton bone", "cross_reference")
        guide = array(part.get("guide"), f"{part_path}.guide")
        if not 2 <= len(guide) <= 8:
            fail(f"{part_path}.guide", "must contain 2 to 8 anchors", "length")
        identities: set[str] = set()
        for index, anchor in enumerate(guide):
            normalized = _anchor(anchor, f"{part_path}.guide[{index}]", side, entities)
            identity = canonical_sha256(normalized)
            if identity in identities:
                fail(f"{part_path}.guide[{index}]", "anchor is duplicated", "duplicate")
            identities.add(identity)
        _anchor(part.get("pivot"), f"{part_path}.pivot", side, entities)


def _anchor(value: Any, path: str, side: str, entities: ResolvedEntities) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        fail(path, "anchor must be a JSON object", "type")
    kind = value.get("kind")
    if kind == "joint":
        anchor = object_exact(value, required={"kind", "joint_id"}, path=path)
        joint_id = safe_id(anchor.get("joint_id"), f"{path}.joint_id")
        if joint_id not in entities.joints or entities.joints[joint_id]["side"] not in {side, "center"}:
            fail(f"{path}.joint_id", "must reference a compatible skeleton joint", "cross_reference")
        return anchor
    if kind != "manual_proxy":
        fail(f"{path}.kind", "anchor kind is unsupported", "enum")
    anchor = object_exact(
        value,
        required={"kind", "proxy_id", "xy", "label", "reason"},
        optional={"proxy_for_joint_id"},
        path=path,
    )
    proxy_id = safe_id(anchor.get("proxy_id"), f"{path}.proxy_id")
    if not proxy_id.endswith(f".{side}"):
        fail(f"{path}.proxy_id", "manual proxy must use the part side suffix", "side")
    point(anchor.get("xy"), f"{path}.xy", entities.width, entities.height)
    text(anchor.get("label"), f"{path}.label", maximum=96, nonblank=True)
    text(anchor.get("reason"), f"{path}.reason", maximum=1000, nonblank=True)
    if "proxy_for_joint_id" in anchor:
        joint_id = safe_id(anchor["proxy_for_joint_id"], f"{path}.proxy_for_joint_id")
        if joint_id not in entities.joints:
            fail(f"{path}.proxy_for_joint_id", "references an unknown joint", "cross_reference")
    return anchor


def _split_decision(value: Any, path: str, layer: Mapping[str, Any]) -> None:
    decision = object_exact(
        value,
        required={
            "action", "split_artifact_sha256", "operation_config_sha256",
            "review_target_sha256", "analysis", "binding_status",
        },
        optional={"reason"},
        path=path,
    )
    action = decision.get("action")
    if action not in _SPLIT_ACTIONS:
        fail(f"{path}.action", "split action is unsupported", "enum")
    for field in ("split_artifact_sha256", "operation_config_sha256", "review_target_sha256"):
        sha256(decision.get(field), f"{path}.{field}")
    analysis = object_exact(
        decision.get("analysis"),
        required={
            "layer_manifest_sha256", "resolved_snapshot_sha256", "split_spec_sha256",
            "algorithm_id", "algorithm_version",
        },
        path=f"{path}.analysis",
    )
    for field in ("layer_manifest_sha256", "resolved_snapshot_sha256", "split_spec_sha256"):
        sha256(analysis.get(field), f"{path}.analysis.{field}")
    safe_id(analysis.get("algorithm_id"), f"{path}.analysis.algorithm_id")
    version(analysis.get("algorithm_version"), f"{path}.analysis.algorithm_version")
    status = decision.get("binding_status")
    if status not in {"current", "stale"}:
        fail(f"{path}.binding_status", "must be current or stale", "enum")
    if action == "reject":
        text(decision.get("reason"), f"{path}.reason", maximum=1000, nonblank=True)
    elif "reason" in decision:
        text(decision["reason"], f"{path}.reason", maximum=1000, nonblank=True)
    if status == "current":
        spec = layer.get("split_spec")
        if layer.get("side") != "bilateral" or layer.get("disposition") not in _SPLIT_DISPOSITIONS \
                or not isinstance(spec, Mapping):
            fail(path, "current split decision no longer has current split authoring", "stale")
        if analysis.get("split_spec_sha256") != canonical_sha256(spec):
            fail(f"{path}.analysis.split_spec_sha256", "does not match current split_spec", "stale")


def _forbid(value: Mapping[str, Any], path: str, fields: set[str]) -> None:
    present = sorted(set(value) & fields)
    if present:
        fail(f"{path}.{present[0]}", "field is forbidden for this review state", "forbidden")
