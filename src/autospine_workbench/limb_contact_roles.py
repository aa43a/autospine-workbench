"""Semantic layer grouping and absence flags for limb contact analysis."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .contact_statistics import ContactEvidence
from .limb_evidence_layers import LimbEvidenceSet


CONTACT_RELATIONS = (
    ("torso_arm", "torso", "arm", "shoulder"),
    ("pelvis_leg", "pelvis", "leg", "hip"),
    ("leg_foot", "leg", "foot", "ankle"),
)
SIDES = ("left", "right")
_ROLE_TOKENS = (
    ("torso", ("torso",)),
    ("pelvis", ("pelvis",)),
    ("foot", ("foot",)),
    ("leg", ("leg",)),
    ("arm", ("arm", "hand")),
)
_SIMPLE_MISSING = {
    "torso": ("TORSO_REFERENCE_LAYER_MISSING", "shoulder"),
    "arm": ("ARM_LAYER_MISSING", "shoulder"),
    "pelvis": ("PELVIS_REFERENCE_LAYER_MISSING", "hip"),
    "foot": ("FOOT_LAYER_MISSING", "ankle"),
}


@dataclass(frozen=True, slots=True)
class PelvisLegDecision:
    keep: bool
    flags: tuple[str, ...]


def group_contact_layers(evidence: LimbEvidenceSet) -> dict[str, list[str]]:
    """Group loaded alpha layers by their contact-specific semantic role."""

    groups = {role: [] for role, _ in _ROLE_TOKENS}
    for layer_id in sorted(evidence.geometries):
        layer = evidence.layers_by_id.get(layer_id)
        role = _contact_role(str(layer.get("canonical_role") or "")) if layer else None
        if role is not None:
            groups[role].append(layer_id)
    return groups


def missing_contact_role_flags(
    groups: Mapping[str, list[str]],
) -> tuple[set[str], dict[str, set[str]]]:
    """Return explicit QA and per-joint flags without inventing shortcut edges."""

    qa_flags: set[str] = set()
    joint_flags: dict[str, set[str]] = {}
    for role, (flag, joint_name) in _SIMPLE_MISSING.items():
        if not groups[role]:
            qa_flags.add(flag)
            add_bilateral_flag(joint_flags, joint_name, flag)
    if not groups["leg"]:
        leg_flags = {
            "PELVIS_LEG_EDGE_UNOBSERVABLE",
            "LEG_FOOT_EDGE_UNOBSERVABLE",
            "PELVIS_FOOT_SHORTCUT_FORBIDDEN",
        }
        qa_flags.update(leg_flags)
        for flag in leg_flags:
            joint_name = "hip" if flag.startswith("PELVIS_LEG") else "ankle"
            add_bilateral_flag(joint_flags, joint_name, flag)
    return qa_flags, joint_flags


def contact_side_hint(parent: Mapping[str, Any], child: Mapping[str, Any]) -> str:
    """Return an explicit side, bilateral, or conflict from layer semantics."""

    layer_sides = (
        str(parent.get("side") or "unknown"),
        str(child.get("side") or "unknown"),
    )
    explicit = [side for side in layer_sides if side in SIDES]
    if len(set(explicit)) > 1:
        return "conflict"
    return explicit[0] if explicit else "bilateral"


def classify_pelvis_leg_contact(
    contact: ContactEvidence,
    child_layer: Mapping[str, Any],
    child_geometry: Any,
    config: Mapping[str, int | float],
) -> PelvisLegDecision:
    """Apply the fixed deep-overlap rejection and ambiguity thresholds."""

    child_height = _contact_layer_height(child_layer, child_geometry)
    height_ratio = contact.bbox_xywh[3] / child_height
    rejected = contact.mode == "overlap" and (
        contact.overlap_ratio_b >= config["pelvis_leg_reject_overlap_ratio"]
        or height_ratio >= config["pelvis_leg_reject_height_ratio"]
    )
    if rejected:
        return PelvisLegDecision(False, ("PELVIS_LEG_OVERLAP_TOO_DEEP",))
    ambiguous = contact.mode == "overlap" and (
        contact.overlap_ratio_b >= config["pelvis_leg_warn_overlap_ratio"]
        or height_ratio >= config["pelvis_leg_warn_height_ratio"]
    )
    flags = ("PELVIS_LEG_CONTACT_AMBIGUOUS",) if ambiguous else ()
    return PelvisLegDecision(True, flags)


def _contact_layer_height(layer: Mapping[str, Any], geometry: Any) -> int:
    bbox = layer.get("bbox")
    height = bbox.get("height") if isinstance(bbox, Mapping) else None
    if isinstance(height, int) and not isinstance(height, bool) and height > 0:
        return height
    boxes = [component.bbox_xywh for component in geometry.components]
    top = min((box[1] for box in boxes), default=0)
    bottom = max((box[1] + box[3] for box in boxes), default=1)
    return max(1, bottom - top)


def add_joint_flag(mapping: dict[str, set[str]], joint_id: str, flag: str) -> None:
    mapping.setdefault(joint_id, set()).add(flag)


def add_bilateral_flag(
    mapping: dict[str, set[str]], joint_name: str, flag: str
) -> None:
    for side in SIDES:
        add_joint_flag(mapping, f"{joint_name}.{side}", flag)


def _contact_role(value: str) -> str | None:
    normalized = value.replace("-", "_").split(".")[-1]
    for role, tokens in _ROLE_TOKENS:
        if any(token in normalized for token in tokens):
            return role
    return None
