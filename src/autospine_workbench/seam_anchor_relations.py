"""Bind reviewed semantics to setup-visible P3 attachments; choose nothing."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import re
from typing import Any

from .limb_contact_roles import CONTACT_RELATIONS, SIDES
from .resolved_project import canonical_sha256
from .seam_anchor_profile import MAX_RELATION_CANDIDATE_PAIRS
from .seam_anchor_relation_pairs import materialize_supported_attachment_pairs


_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SUPPORTED_TYPES = frozenset({"region", "mesh"})
_NEUTRAL_SIDES = frozenset({"center", "bilateral"})
_VALID_SIDES = frozenset({*SIDES, *_NEUTRAL_SIDES})
ROLE_TOKEN_PROFILE = (
    ("torso", ("torso",)), ("pelvis", ("pelvis",)),
    ("foot", ("foot",)), ("leg", ("leg",)),
    ("arm", ("arm", "hand")),
)
PARENT_NEUTRAL_RELATIONS = frozenset({"torso_arm", "pelvis_leg"})

class SeamAnchorRelationError(ValueError):
    """Raised when the two admitted documents are not exactly cross-bound."""


@dataclass(frozen=True, slots=True)
class _Attachment:
    identifier: str
    kind: str
    sources: tuple[str, ...]
    role: str | None
    side: str | None
    role_evidence: frozenset[str]
    side_evidence: frozenset[str]
    issues: tuple[str, ...]


def build_seam_relationship_inventory(
    manifest: Mapping[str, Any], rig: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """Return fixed torso/limb seam rows without inventing side or decisions."""

    manifest = _mapping(manifest, "Layer Manifest")
    rig = _mapping(rig, "P3 RigIR")
    _require_documents(manifest, rig)
    layers = _layers(manifest.get("layers"))
    slots = _slots(rig.get("slots"), rig.get("skins"))
    raw_attachments = _objects(rig.get("attachments"), "P3 attachments")
    source_counts = Counter(
        source
        for item in raw_attachments
        for source in _source_ids(item.get("source_layer_ids"), strict=False)
    )
    attachments = tuple(sorted(
        (_attachment(item, layers, slots, source_counts)
         for item in raw_attachments),
        key=lambda item: item.identifier,
    ))
    role_sides = _manifest_role_sides(layers)
    rows = [
        _relationship_row(
            relation, parent_role, child_role, joint, side,
            attachments, role_sides,
        )
        for relation, parent_role, child_role, joint in CONTACT_RELATIONS
        for side in SIDES
    ]
    if len(rows) != 6:
        raise SeamAnchorRelationError("Pinned seam relationship profile changed")
    return rows


def _relationship_row(
    relation, parent_role, child_role, joint, side, attachments, role_sides
):
    parent_neutral = relation in PARENT_NEUTRAL_RELATIONS
    reasons: set[str] = set()
    _role_availability(
        reasons, "PARENT", parent_role, side, parent_neutral, role_sides
    )
    _role_availability(reasons, "CHILD", child_role, side, False, role_sides)
    parents = _eligible(
        attachments, parent_role, side, parent_neutral, "PARENT", reasons
    )
    children = _eligible(
        attachments, child_role, side, False, "CHILD", reasons
    )
    pairs, pair_reasons = materialize_supported_attachment_pairs(
        parents, children, MAX_RELATION_CANDIDATE_PAIRS
    )
    reasons.update(pair_reasons)
    pairs.sort(key=lambda item: (
        item["parent_attachment_id"], item["child_attachment_id"],
        tuple(item["parent_source_layer_ids"]),
        tuple(item["child_source_layer_ids"]),
    ))
    if len(pairs) > 1:
        reasons.add("MULTIPLE_CANDIDATE_PAIRS")
    if not pairs:
        reasons.add("NO_SUPPORTED_CANDIDATE_PAIR")
    return {
        "relationship_id": f"seam.{relation}.{side}",
        "relation": relation,
        "joint": f"{joint}.{side}",
        "side": side,
        "candidate_pairs": pairs,
        "reason_codes": sorted(reasons),
    }


def _eligible(attachments, role, side, neutral, prefix, reasons):
    result: list[_Attachment] = []
    for item in attachments:
        if role not in item.role_evidence:
            continue
        if not _side_relevant(item.side_evidence, side, neutral):
            continue
        for issue in item.issues:
            reasons.add(f"{prefix}_{issue}")
        if item.issues or item.role != role or not _side_matches(item.side, side, neutral):
            continue
        result.append(item)
    return result


def _attachment(raw, layers, slots, source_counts) -> _Attachment:
    identifier = _safe_id(raw.get("id"), "attachment id")
    sources = _source_ids(raw.get("source_layer_ids"), strict=True)
    source_layers = [layers.get(source) for source in sources]
    role_evidence = frozenset(
        role for layer in source_layers if layer is not None
        for role in _role_families(layer["role"])
    )
    side_evidence = frozenset(
        layer["side"] for layer in source_layers
        if layer is not None and layer["side"] in _VALID_SIDES
    )
    issues: set[str] = set()
    if any(layer is None for layer in source_layers):
        issues.add("SOURCE_LAYER_MISSING")
    if any(source_counts[source] != 1 for source in sources):
        issues.add("SOURCE_LAYER_CROSSWIRE")
    role = next(iter(role_evidence)) if len(role_evidence) == 1 else None
    if not role_evidence:
        issues.add("SOURCE_ROLE_MISSING_OR_UNSUPPORTED")
    elif len(role_evidence) != 1:
        issues.add("SOURCE_ROLE_CONFLICT")
    side = _combined_side(side_evidence)
    if not side_evidence:
        issues.add("SOURCE_SIDE_MISSING_OR_UNSUPPORTED")
    elif side is None:
        issues.add("SOURCE_SIDE_CONFLICT")
    kind = raw.get("type") if isinstance(raw.get("type"), str) else "invalid"
    if kind not in _SUPPORTED_TYPES:
        issues.add("ATTACHMENT_TYPE_UNSUPPORTED")
    slot_id = raw.get("slot")
    visible = slots.get(slot_id) == identifier
    if not visible or any(
        layer is not None and layer["visible"] is not True
        for layer in source_layers
    ):
        issues.add("ATTACHMENT_NOT_SETUP_VISIBLE")
    return _Attachment(
        identifier, kind, sources, role, side,
        role_evidence, side_evidence, tuple(sorted(issues)),
    )


def _layers(value) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for raw in _objects(value, "Layer Manifest layers"):
        layer_id = _safe_id(raw.get("layer_id"), "layer id")
        if layer_id in result:
            raise SeamAnchorRelationError(f"Duplicate manifest layer id: {layer_id}")
        semantic = _mapping(raw.get("semantic"), f"layer {layer_id} semantic")
        source = _mapping(raw.get("source"), f"layer {layer_id} source")
        side = semantic.get("side")
        role = semantic.get("canonical_role")
        if not isinstance(side, str) or not isinstance(role, str):
            raise SeamAnchorRelationError(f"Layer {layer_id} semantics are invalid")
        if not isinstance(source.get("visible"), bool):
            raise SeamAnchorRelationError(f"Layer {layer_id} visibility is invalid")
        result[layer_id] = {"role": role, "side": side, "visible": source["visible"]}
    return result


def _slots(value, skins) -> dict[str, str | None]:
    default = _mapping(_mapping(skins, "P3 skins").get("default"), "default skin")
    result: dict[str, str | None] = {}
    for raw in _objects(value, "P3 slots"):
        slot_id = _safe_id(raw.get("id"), "slot id")
        if slot_id in result:
            raise SeamAnchorRelationError(f"Duplicate P3 slot id: {slot_id}")
        setup = raw.get("setup_attachment")
        members = default.get(slot_id)
        visible = setup if (
            isinstance(setup, str) and isinstance(members, list) and setup in members
        ) else None
        result[slot_id] = visible
    return result


def _manifest_role_sides(layers):
    result: dict[str, set[str]] = {}
    for layer in layers.values():
        for role in _role_families(layer["role"]):
            result.setdefault(role, set()).add(layer["side"])
    return result


def _role_availability(reasons, prefix, role, side, neutral, role_sides):
    sides = role_sides.get(role, set())
    if not sides:
        reasons.add(f"{prefix}_ROLE_MISSING")
    elif not any(_side_matches(item, side, neutral) for item in sides):
        reasons.add(f"{prefix}_SIDE_UNAVAILABLE")


def _combined_side(sides: frozenset[str]) -> str | None:
    explicit = sides & frozenset(SIDES)
    neutral = sides & _NEUTRAL_SIDES
    if len(explicit) > 1 or (explicit and neutral):
        return None
    if explicit:
        return next(iter(explicit))
    if "bilateral" in neutral:
        return "bilateral"
    return "center" if neutral else None


def _side_matches(value, side, neutral):
    return value == side or bool(neutral and value in _NEUTRAL_SIDES)


def _side_relevant(values, side, neutral):
    return side in values or bool(neutral and values & _NEUTRAL_SIDES)


def _role_families(value: str) -> frozenset[str]:
    tokens = set(re.split(r"[._-]+", value.casefold()))
    return frozenset(
        role for role, aliases in ROLE_TOKEN_PROFILE
        if tokens.intersection(aliases)
    )


def _require_documents(manifest, rig):
    if manifest.get("format") != "autospine-layer-manifest" \
            or manifest.get("format_version") != 1 \
            or _mapping(manifest.get("qa"), "Layer Manifest QA").get("status") != "passed":
        raise SeamAnchorRelationError("Layer Manifest is not admitted")
    if rig.get("format") != "autospine-rig-ir" or rig.get("format_version") != 1 \
            or _mapping(rig.get("qa"), "P3 QA").get("status") != "passed":
        raise SeamAnchorRelationError("P3 RigIR is not admitted")
    source = _mapping(rig.get("source"), "P3 source")
    if source.get("layer_manifest_sha256") != canonical_sha256(manifest):
        raise SeamAnchorRelationError("P3 RigIR references another Layer Manifest")


def _source_ids(value, *, strict):
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        if strict:
            raise SeamAnchorRelationError("Attachment source layers must be an array")
        return ()
    if strict and (not value or any(not isinstance(item, str) for item in value)):
        raise SeamAnchorRelationError("Attachment source layers are invalid")
    if strict and len(set(value)) != len(value):
        raise SeamAnchorRelationError("Attachment source layers are duplicated")
    return tuple(sorted(item for item in value if isinstance(item, str)))


def _safe_id(value, label):
    if not isinstance(value, str) or not _SAFE_ID.fullmatch(value):
        raise SeamAnchorRelationError(f"{label} must be a safe id")
    return value


def _mapping(value, label):
    if not isinstance(value, Mapping):
        raise SeamAnchorRelationError(f"{label} must be an object")
    return value


def _objects(value, label):
    if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
        raise SeamAnchorRelationError(f"{label} must be an object array")
    return tuple(value)
