"""Deterministic setup-alpha geometry for P10.5a seam options."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .contact_geometry import contact_between_alpha
from .contact_statistics import ContactEvidence
from .seam_anchor_alpha_cache import (
    SeamAnchorAlphaCacheError,
    build_seam_alpha_index,
)
from .seam_anchor_candidate_profile import (
    CONTACT_MAX_GAP_PX,
    MAX_OPTIONS_PER_RELATION,
    MAX_RELATION_CANDIDATE_PAIRS,
    MAX_TOTAL_OPTIONS,
    option_evidence_sha256,
    relationship_evidence_sha256,
)
from .seam_anchor_inputs import SeamAnchorInputs
from .seam_anchor_lobes import SeamAnchorLobeError, isolate_overlap_lobe_runs
from .seam_anchor_locators import SeamAnchorLocatorError
from .seam_anchor_relations import (
    SeamAnchorRelationError,
    build_seam_relationship_inventory,
)
from .seam_anchor_sampling import (
    DEFAULT_ANCHOR_PAIRS,
    MAX_RUNS_PER_MASK,
    SeamAnchorSamplingError,
    SeamAnchorUnsupportedError,
    materialize_sampled_locator_pairs,
    sample_common_alpha_pairs,
)


class SeamAnchorCandidateGeometryError(ValueError):
    """Raised when admitted static evidence cannot be compiled exactly."""


def derive_seam_candidate_relationships(
    inputs: SeamAnchorInputs,
) -> list[dict[str, Any]]:
    """Compile all fixed relationship options without choosing one."""

    try:
        if type(inputs) is not SeamAnchorInputs:
            raise SeamAnchorCandidateGeometryError(
                "Seam candidate geometry requires admitted static inputs"
            )
        rig, manifest = inputs.rig, inputs.manifest
        attachments = _attachment_index(rig)
        inventory = build_seam_relationship_inventory(manifest, rig)
        for raw in inventory:
            if len(raw["candidate_pairs"]) > MAX_RELATION_CANDIDATE_PAIRS:
                raise SeamAnchorCandidateGeometryError(
                    "Seam relationship candidate-pair budget exceeded"
                )
        referenced = {
            pair[field]
            for raw in inventory for pair in raw["candidate_pairs"]
            for field in ("parent_attachment_id", "child_attachment_id")
        }
        geometry = build_seam_alpha_index(
            inputs, attachments, referenced
        )
        relationships, total = [], 0
        for raw in inventory:
            pairs = raw["candidate_pairs"]
            options = _relationship_options(
                raw, pairs, attachments, geometry
            )
            total += len(options)
            if len(options) > MAX_OPTIONS_PER_RELATION \
                    or total > MAX_TOTAL_OPTIONS:
                raise SeamAnchorCandidateGeometryError(
                    "Seam candidate option budget exceeded"
                )
            reasons = set(raw["reason_codes"])
            for option in options:
                reasons.update(option["reason_codes"])
            payload = {
                "relationship_id": raw["relationship_id"],
                "relation": raw["relation"],
                "joint": raw["joint"],
                "side": raw["side"],
                "status": "review_required" if any(
                    option["status"] == "candidate" for option in options
                ) else "unobservable",
                "reason_codes": sorted(reasons),
                "options": options,
            }
            payload["evidence_sha256"] = relationship_evidence_sha256(
                payload
            )
            relationships.append(payload)
        return relationships
    except SeamAnchorCandidateGeometryError:
        raise
    except _FAILURES as exc:
        raise SeamAnchorCandidateGeometryError(
            f"Static seam candidate geometry failed: {exc}"
        ) from exc


def _relationship_options(row, pairs, attachments, geometry):
    options = []
    for pair in pairs:
        parent = _bound_attachment(pair, "parent", attachments)
        child = _bound_attachment(pair, "child", attachments)
        first, second = geometry[parent["id"]], geometry[child["id"]]
        if first is None or second is None:
            options.append(_option(
                row, len(options), parent, child,
                status="unavailable", reasons=["SAMPLING_BUDGET_EXCEEDED"],
            ))
            continue
        runs_a, runs_b = first.canvas_runs(), second.canvas_runs()
        if len(runs_a) > MAX_RUNS_PER_MASK \
                or len(runs_b) > MAX_RUNS_PER_MASK:
            options.append(_option(
                row, len(options), parent, child,
                status="unavailable", reasons=["SAMPLING_BUDGET_EXCEEDED"],
            ))
            continue
        analysis = contact_between_alpha(
            first, second, max_gap=CONTACT_MAX_GAP_PX
        )
        if not analysis.contacts:
            reasons = list(analysis.qa_flags) or ["CONTACT_UNOBSERVABLE"]
            options.append(_option(
                row, len(options), parent, child,
                status="unavailable", reasons=reasons,
            ))
            continue
        for contact in analysis.contacts:
            options.append(_contact_option(
                row, len(options), parent, child,
                first, second, contact,
            ))
            if len(options) > MAX_OPTIONS_PER_RELATION:
                raise SeamAnchorCandidateGeometryError(
                    "Seam candidate option budget exceeded"
                )
    return options


def _contact_option(
    row, option_index, parent, child,
    alpha_a, alpha_b, contact,
):
    evidence = _contact_evidence(contact)
    if contact.mode != "overlap":
        return _option(
            row, option_index, parent, child,
            status="unavailable",
            reasons=["GAP_LOCATOR_UNSUPPORTED_IN_V1"],
            evidence=evidence,
        )
    lobe = isolate_overlap_lobe_runs(
        alpha_a.canvas_runs(), alpha_b.canvas_runs(), contact
    )
    sampling = sample_common_alpha_pairs(
        lobe, lobe, contact.bbox_xywh,
        requested_pair_count=DEFAULT_ANCHOR_PAIRS,
    )
    if sampling.status != "available":
        if sampling.reason_code == "common_alpha_gap":
            raise SeamAnchorCandidateGeometryError(
                "Isolated overlap lobe unexpectedly has no common alpha"
            )
        return _option(
            row, option_index, parent, child,
            status="unavailable",
            reasons=[str(sampling.reason_code).upper()], evidence=evidence,
            axis=sampling.principal_axis,
            sampling_profile=sampling.sampling_profile,
        )
    try:
        sampled = materialize_sampled_locator_pairs(
            sampling, parent, child
        )
        anchors = [{
            "pair_id": item["pair_id"],
            "parent": item["a"],
            "child": item["b"],
        } for item in sampled]
    except SeamAnchorUnsupportedError as exc:
        raise SeamAnchorCandidateGeometryError(
            "Supported relationship produced an unsupported locator pair"
        ) from exc
    except SeamAnchorLocatorError:
        return _option(
            row, option_index, parent, child,
            status="unavailable", reasons=["LOCATOR_UNREPRESENTABLE"],
            evidence=evidence, axis=sampling.principal_axis,
            sampling_profile=sampling.sampling_profile,
        )
    return _option(
        row, option_index, parent, child,
        status="candidate", reasons=[], evidence=evidence,
        axis=sampling.principal_axis,
        sampling_profile=sampling.sampling_profile, anchors=anchors,
    )


def _option(
    row, option_index, parent, child, *, status, reasons,
    evidence=None, axis=None, sampling_profile=None, anchors=None,
):
    payload = {
        "option_id": f"{row['relationship_id']}.option.{option_index:03d}",
        "parent_attachment_id": parent["id"],
        "child_attachment_id": child["id"],
        "parent_attachment_type": parent["type"],
        "child_attachment_type": child["type"],
        "status": status,
        "reason_codes": sorted(set(reasons)),
        "contact_evidence": evidence,
        "principal_axis": axis,
        "sampling_profile": sampling_profile,
        "anchors": anchors or [],
    }
    payload["evidence_sha256"] = option_evidence_sha256(payload)
    return payload


def _contact_evidence(item: ContactEvidence) -> dict[str, Any]:
    return {
        "contact_id": item.id,
        "mode": item.mode,
        "area": item.area,
        "bbox_xywh": list(item.bbox_xywh),
        "centroid_xy": list(item.centroid_xy),
        "variance_xy": list(item.variance_xy),
        "representative_xy": list(item.representative_xy),
        "error_radius_px": item.error_radius,
        "overlap_ratios": [item.overlap_ratio_a, item.overlap_ratio_b],
        "gap_distance_px": item.gap_distance_px,
        "endpoints_xy": [list(item.source_xy_a), list(item.source_xy_b)],
    }


def _attachment_index(rig):
    rows = rig.get("attachments")
    if not isinstance(rows, list):
        raise SeamAnchorCandidateGeometryError(
            "P3 attachment inventory is invalid"
        )
    result = {}
    for row in rows:
        if not isinstance(row, Mapping) or row.get("id") in result:
            raise SeamAnchorCandidateGeometryError(
                "P3 attachment inventory is invalid"
            )
        result[row["id"]] = row
    return result


def _bound_attachment(pair, prefix, attachments):
    identifier = pair[f"{prefix}_attachment_id"]
    attachment = attachments.get(identifier)
    if attachment is None \
            or attachment.get("type") != pair[f"{prefix}_attachment_type"]:
        raise SeamAnchorCandidateGeometryError(
            "Semantic relationship attachment changed"
        )
    return attachment


_FAILURES = (
    AttributeError, KeyError, OverflowError, RecursionError,
    SeamAnchorAlphaCacheError, SeamAnchorLobeError, SeamAnchorRelationError,
    SeamAnchorSamplingError, TypeError, UnicodeError, ValueError,
)
