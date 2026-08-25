"""Pose-conditioned contact evidence for torso and limb alpha layers."""

from __future__ import annotations

from dataclasses import replace
import math
from typing import Any, Mapping

from .contact_geometry import contact_between_alpha
from .contact_statistics import ContactSections, ContactSite
from .limb_contact_roles import (
    CONTACT_RELATIONS,
    SIDES,
    add_bilateral_flag,
    add_joint_flag,
    classify_pelvis_leg_contact,
    contact_side_hint,
    group_contact_layers,
    missing_contact_role_flags,
)
from .limb_evidence_layers import LimbEvidenceSet
from .limb_geometry_matching import assign_contact_sites, geometry_config
from .pose_observations import PoseObservationSet

def analyze_limb_contacts(
    evidence: LimbEvidenceSet,
    observations: PoseObservationSet,
    canvas_size: tuple[int, int],
    config: Mapping[str, Any],
) -> ContactSections:
    """Return deterministic torso/limb contact evidence without screen-x guesses."""

    if (
        not isinstance(canvas_size, tuple)
        or len(canvas_size) != 2
        or any(
            not isinstance(value, int) or isinstance(value, bool) or value < 1
            for value in canvas_size
        )
    ):
        raise ValueError("canvas_size must be a positive integer pair")
    width, height = canvas_size
    if observations.canvas_size != (width, height):
        raise ValueError("pose observations do not match the contact canvas")
    settings = geometry_config(config)
    diagonal = math.hypot(width, height)
    max_gap = min(
        float(settings["contact_max_gap_px"]),
        diagonal * float(settings["contact_max_gap_ratio"]),
    )
    groups = group_contact_layers(evidence)
    qa_flags, joint_flags = missing_contact_role_flags(groups)
    assigned: list[tuple[ContactSite, str]] = []

    for relation, parent_role, child_role, joint_name in CONTACT_RELATIONS:
        relation_sites: list[tuple[ContactSite, str]] = []
        if not groups[parent_role] or not groups[child_role]:
            continue
        for parent_id in groups[parent_role]:
            for child_id in groups[child_role]:
                hint = contact_side_hint(
                    evidence.layers_by_id[parent_id], evidence.layers_by_id[child_id]
                )
                if hint == "conflict":
                    qa_flags.add("CONTACT_LAYER_SIDE_CONFLICT")
                    continue
                analysis = contact_between_alpha(
                    evidence.geometries[parent_id],
                    evidence.geometries[child_id],
                    max_gap=max_gap,
                )
                qa_flags.update(analysis.qa_flags)
                sites = [
                    ContactSite(relation, joint_name, (parent_id, child_id), item)
                    for item in analysis.contacts
                ]
                if relation == "pelvis_leg":
                    sites = _gate_pelvis_leg(
                        sites,
                        evidence.layers_by_id[child_id],
                        evidence.geometries[child_id],
                        qa_flags,
                        joint_flags,
                        hint,
                        settings,
                    )
                relation_sites.extend(
                    _assign_sites(
                        sites,
                        hint,
                        observations,
                        qa_flags,
                        joint_flags,
                        settings,
                        diagonal,
                    )
                )
        if not relation_sites:
            flag = f"{relation.upper()}_EDGE_UNOBSERVABLE"
            qa_flags.add(flag)
            add_bilateral_flag(joint_flags, joint_name, flag)
        assigned.extend(relation_sites)

    assigned.sort(
        key=lambda item: (
            item[0].relation,
            f"{item[0].joint_name}.{item[1]}",
            _site_key(item[0]),
        )
    )
    contacts, refs = _materialize(assigned, joint_flags)
    flags = {key: sorted(value) for key, value in sorted(joint_flags.items()) if value}
    return ContactSections(contacts, refs, flags, qa_flags)

def _gate_pelvis_leg(
    sites: list[ContactSite],
    child_layer: Mapping[str, Any],
    child_geometry: Any,
    qa: set[str],
    joint_flags: dict[str, set[str]],
    hint: str,
    config: Mapping[str, int | float],
) -> list[ContactSite]:
    kept: list[ContactSite] = []
    for site in sites:
        decision = classify_pelvis_leg_contact(
            site.evidence, child_layer, child_geometry, config
        )
        qa.update(decision.flags)
        if not decision.keep:
            flag = decision.flags[0]
            if hint in SIDES:
                add_joint_flag(joint_flags, f"hip.{hint}", flag)
            else:
                add_bilateral_flag(joint_flags, "hip", flag)
            continue
        kept.append(replace(site, flags=decision.flags) if decision.flags else site)
    return kept


def _assign_sites(
    sites: list[ContactSite],
    hint: str,
    observations: PoseObservationSet,
    qa: set[str],
    joint_flags: dict[str, set[str]],
    config: Mapping[str, int | float],
    diagonal: float,
) -> list[tuple[ContactSite, str]]:
    if not sites:
        return []
    joint_name = sites[0].joint_name
    if joint_name == "shoulder" and len(sites) > 1:
        flag = "SHOULDER_MULTIPLE_CONTACT_LOBES_RETAINED"
        qa.add(flag)
        sites = [
            replace(site, flags=tuple(sorted(set(site.flags) | {flag})))
            for site in sites
        ]
    if hint in SIDES:
        joint_id = f"{joint_name}.{hint}"
        if joint_id not in observations.joints:
            add_joint_flag(joint_flags, joint_id, "CONTACT_POSE_JOINT_MISSING")
        return [(site, hint) for site in sites]
    available = [
        side for side in SIDES if f"{joint_name}.{side}" in observations.joints
    ]
    if not available:
        flag = "BILATERAL_CONTACT_POSE_MISSING"
        qa.add(flag)
        add_bilateral_flag(joint_flags, joint_name, flag)
        return []
    costs = {
        side: {
            site: _pose_distance(site, joint_name, side, observations)
            for site in sites
        }
        for side in available
    }
    assignment = assign_contact_sites(
        costs, sites, diagonal, site_key=_site_key
    )
    primary = [
        (site, side) for side, site in sorted(assignment.primary.items())
    ]
    if (
        assignment.margin_ratio is not None
        and assignment.margin_ratio < config["contact_assignment_margin_ratio"]
    ):
        flag = "CONTACT_SIDE_ASSIGNMENT_AMBIGUOUS"
        qa.add(flag)
        add_bilateral_flag(joint_flags, joint_name, flag)
    if len(primary) < len(SIDES):
        flag = "BILATERAL_CONTACT_UNDERDETERMINED"
        qa.add(flag)
        assigned_sides = {side for _, side in primary}
        for side in SIDES:
            if side not in assigned_sides:
                add_joint_flag(joint_flags, f"{joint_name}.{side}", flag)
    output = list(primary)
    for site, side in assignment.extras:
        flag = (
            "SHOULDER_MULTIPLE_CONTACT_LOBES_RETAINED"
            if joint_name == "shoulder"
            else "EXTRA_CONTACT_LOBE_AMBIGUOUS"
        )
        qa.add(flag)
        flags = tuple(sorted(set(site.flags) | {flag}))
        output.append((replace(site, flags=flags), side))
    return output


def _pose_distance(
    site: ContactSite, joint_name: str, side: str, observations: PoseObservationSet
) -> float:
    observation = observations.joints[f"{joint_name}.{side}"]
    return math.dist(site.evidence.representative_xy, (observation.x, observation.y))


def _site_key(site: ContactSite) -> tuple[Any, ...]:
    item = site.evidence
    return site.relation, site.layer_ids, item.id, item.bbox_xywh, item.representative_xy


def _materialize(
    assigned: list[tuple[ContactSite, str]],
    joint_flags: dict[str, set[str]],
) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    contacts: list[dict[str, Any]] = []
    refs: dict[str, list[str]] = {}
    for index, (site, side) in enumerate(assigned):
        contact_id = f"contact.{site.relation}.{index:03d}"
        joint_id = f"{site.joint_name}.{side}"
        contacts.append(
            site.evidence.to_contract(
                contact_id=contact_id,
                joint_id=joint_id,
                relation=site.relation,
                layer_ids=site.layer_ids,
                flags=site.flags,
            )
        )
        refs.setdefault(joint_id, []).append(contact_id)
        joint_flags.setdefault(joint_id, set()).update(site.flags)
    contacts.sort(key=lambda item: item["contact_id"])
    return contacts, {key: sorted(value) for key, value in sorted(refs.items())}
