"""Dependency-free semantic validation for alpha geometry evidence v1."""

from __future__ import annotations

import math
from typing import Any, Mapping

from .alpha_evidence_fields import (
    AlphaEvidenceValidationIssue,
    EvidenceFieldChecker as _Check,
    finite as _finite,
    integer as _integer,
    require_sorted_ids as _sorted_ids,
    safe_canonical_sha256 as _canonical_sha,
    valid_role,
    validate_anchors as _anchors,
    validate_budgets as _budgets,
    validate_qa as _qa,
)
from .contracts import DISPOSITION_VALUES, SIDE_VALUES


_OBSERVABILITY = {"visible", "occluded", "merged", "absent", "ambiguous"}
_RELATIONS = {"torso_arm", "pelvis_leg", "leg_foot"}


class AlphaEvidenceValidationError(ValueError):
    def __init__(self, issues: list[AlphaEvidenceValidationIssue]):
        self.issues = tuple(issues)
        super().__init__("; ".join(f"{item.path}: {item.message}" for item in issues))


def require_valid_alpha_geometry_evidence(document: Any, **context: Any) -> None:
    issues = validate_alpha_geometry_evidence(document, **context)
    if issues:
        raise AlphaEvidenceValidationError(issues)


def validate_alpha_geometry_evidence(
    document: Any,
    *,
    project_id: str,
    joint_ids: set[str],
    layer_ids: set[str],
    canvas_width: int,
    canvas_height: int,
) -> list[AlphaEvidenceValidationIssue]:
    check = _Check(canvas_width, canvas_height)
    root = check.obj(
        document,
        "$",
        {"format", "format_version", "project_id", "source", "analysis", "coordinate_system",
         "layers", "paths", "contacts", "observability", "qa"},
    )
    if root.get("format") != "autospine-alpha-geometry-evidence" or root.get("format_version") != 1:
        check.add("$", "version", "unsupported alpha geometry evidence format")
    if root.get("project_id") != project_id or not check.valid_id(root.get("project_id")):
        check.add("$.project_id", "project", "project id does not match")
    source = _source(root.get("source"), check)
    layers = _layers(root.get("layers"), layer_ids, check)
    _analysis(root.get("analysis"), project_id, source, root.get("layers"), check)
    expected_cs = {"origin": "top_left", "x_axis": "right", "y_axis": "down",
                   "units": "pixel", "side_naming": "character_side"}
    coordinate = check.obj(root.get("coordinate_system"), "$.coordinate_system", set(expected_cs))
    if coordinate != expected_cs:
        check.add("$.coordinate_system", "coordinate_system", "unsupported coordinate system")
    paths = _paths(root.get("paths"), joint_ids, layers, check)
    if paths and "pose_observations_sha256" not in source:
        check.add("$.source.pose_observations_sha256", "required", "pose hash is required by paths")
    contacts = _contacts(root.get("contacts"), joint_ids, layers, check)
    _observability(root.get("observability"), joint_ids, paths, contacts, check)
    _qa(root.get("qa"), check)
    return check.issues


def _source(value: Any, check: _Check) -> Mapping[str, Any]:
    fields = {"base_project_sha256", "source_image_sha256", "audit_sha256",
              "pose_observations_sha256"}
    source = check.obj(value, "$.source", fields, {"base_project_sha256", "source_image_sha256"})
    for field, item in source.items():
        if field in fields and not check.valid_sha(item):
            check.add(f"$.source.{field}", "hash", "must be a lowercase SHA-256")
    return source


def _analysis(
    value: Any, project_id: str, source: Mapping[str, Any], layers: Any, check: _Check
) -> None:
    fields = {"provider", "provider_version", "input_sha256", "config_sha256", "run_sha256"}
    analysis = check.obj(value, "$.analysis", fields)
    if not check.valid_id(analysis.get("provider")):
        check.add("$.analysis.provider", "id", "invalid provider id")
    version = analysis.get("provider_version")
    if not isinstance(version, str) or not 1 <= len(version) <= 64:
        check.add("$.analysis.provider_version", "length", "invalid provider version")
    for field in ("input_sha256", "config_sha256", "run_sha256"):
        if not check.valid_sha(analysis.get(field)):
            check.add(f"$.analysis.{field}", "hash", "must be a lowercase SHA-256")
    expected_input = _canonical_sha({"project_id": project_id, "source": source, "layers": layers})
    if expected_input is None:
        check.add("$.analysis.input_sha256", "canonical", "inputs are not strict canonical JSON")
    elif analysis.get("input_sha256") != expected_input:
        check.add("$.analysis.input_sha256", "identity", "input identity is inconsistent")
    expected_run = _canonical_sha({
        "input_sha256": analysis.get("input_sha256"), "provider": analysis.get("provider"),
        "provider_version": version, "config_sha256": analysis.get("config_sha256"),
    })
    if expected_run is None:
        check.add("$.analysis.run_sha256", "canonical", "run inputs are not strict canonical JSON")
    elif analysis.get("run_sha256") != expected_run:
        check.add("$.analysis.run_sha256", "identity", "run identity is inconsistent")


def _layers(value: Any, known: set[str], check: _Check) -> dict[str, tuple[set[int], int]]:
    result: dict[str, tuple[set[int], int]] = {}
    items = check.array(value, "$.layers")
    for index, raw in enumerate(items):
        path = f"$.layers[{index}]"
        layer = check.obj(raw, path, {"layer_id", "raster_sha256", "canonical_role", "side",
                                     "disposition", "alpha_threshold", "foreground_area", "components"})
        layer_id = layer.get("layer_id")
        if not check.valid_id(layer_id) or layer_id not in known:
            check.add(f"{path}.layer_id", "unknown_layer", "layer is not in project")
        if isinstance(layer_id, str) and layer_id in result:
            check.add(f"{path}.layer_id", "duplicate", "layer id is duplicated")
        if not check.valid_sha(layer.get("raster_sha256")):
            check.add(f"{path}.raster_sha256", "hash", "invalid raster SHA-256")
        if not valid_role(layer.get("canonical_role")):
            check.add(f"{path}.canonical_role", "role", "invalid canonical role")
        if layer.get("side") not in SIDE_VALUES:
            check.add(f"{path}.side", "enum", "unsupported character side")
        if layer.get("disposition") not in DISPOSITION_VALUES:
            check.add(f"{path}.disposition", "enum", "unsupported layer disposition")
        threshold, foreground = layer.get("alpha_threshold"), layer.get("foreground_area")
        if not _integer(threshold) or not 1 <= threshold <= 255:
            check.add(f"{path}.alpha_threshold", "bounds", "threshold must lie in [1, 255]")
        if not _integer(foreground) or foreground < 0:
            check.add(f"{path}.foreground_area", "bounds", "area must be non-negative")
        components, total = set(), 0
        for component_index, raw_component in enumerate(check.array(layer.get("components"), f"{path}.components")):
            component_path = f"{path}.components[{component_index}]"
            component = check.obj(raw_component, component_path, {"component_id", "area", "bbox_xywh"})
            component_id, area = component.get("component_id"), component.get("area")
            if not _integer(component_id) or component_id < 0 or component_id in components:
                check.add(f"{component_path}.component_id", "component", "invalid or duplicate component")
            else:
                components.add(component_id)
            if not _integer(area) or area < 1:
                check.add(f"{component_path}.area", "bounds", "component area must be positive")
            else:
                total += area
            check.bbox(component.get("bbox_xywh"), f"{component_path}.bbox_xywh")
        if _integer(foreground) and total != foreground:
            check.add(f"{path}.foreground_area", "identity", "must equal component area sum")
        if isinstance(layer_id, str):
            result[layer_id] = (components, foreground if _integer(foreground) else 0)
    _sorted_ids(items, "layer_id", "$.layers", check)
    return result


def _paths(
    value: Any, joint_ids: set[str], layers: Mapping[str, tuple[set[int], int]], check: _Check
) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    items = check.array(value, "$.paths")
    for index, raw in enumerate(items):
        path = f"$.paths[{index}]"
        item = check.obj(raw, path, {"path_id", "limb_id", "status", "joint_ids", "layer_id",
                     "component_id", "anchors", "polyline_xy", "length_px", "min_clearance_px",
                     "median_clearance_px", "hinge_candidate_xy", "error_radius_px", "budgets", "flags"})
        path_id = item.get("path_id")
        if not check.valid_id(path_id) or path_id in result:
            check.add(f"{path}.path_id", "id", "invalid or duplicate path id")
        joints = item.get("joint_ids")
        if (not isinstance(joints, list) or len(joints) != 3
                or any(not isinstance(value, str) for value in joints) or len(set(joints)) != 3):
            check.add(f"{path}.joint_ids", "shape", "must contain three distinct joint ids")
            joints = []
        for joint_id in joints:
            if joint_id not in joint_ids:
                check.add(f"{path}.joint_ids", "unknown_joint", "joint is not in project")
        if not check.valid_id(item.get("limb_id")):
            check.add(f"{path}.limb_id", "id", "invalid limb id")
        layer_id, component_id = item.get("layer_id"), item.get("component_id")
        if not isinstance(layer_id, str) or layer_id not in layers:
            check.add(f"{path}.layer_id", "unknown_layer", "layer summary is missing")
        elif component_id not in layers[layer_id][0]:
            check.add(f"{path}.component_id", "component", "component is not in layer summary")
        status = item.get("status")
        if status not in {"valid", "unavailable"}:
            check.add(f"{path}.status", "enum", "unsupported path status")
        _anchors(item.get("anchors"), joints, path, status, check)
        polyline = check.points(item.get("polyline_xy"), f"{path}.polyline_xy")
        if len(polyline) > 128:
            check.add(f"{path}.polyline_xy", "budget", "polyline exceeds 128 points")
        metrics = ("length_px", "min_clearance_px", "median_clearance_px", "error_radius_px")
        for field in metrics:
            check.number(item.get(field), f"{path}.{field}", nullable=status == "unavailable")
        hinge = check.point(item.get("hinge_candidate_xy"), f"{path}.hinge_candidate_xy",
                            nullable=status == "unavailable")
        if status == "valid" and (not polyline or hinge not in polyline):
            check.add(f"{path}.polyline_xy", "path", "valid path must include its hinge")
        if status == "unavailable" and polyline:
            check.add(f"{path}.polyline_xy", "path", "unavailable path must be empty")
        if status == "unavailable" and (
            any(item.get(field) is not None for field in metrics) or item.get("hinge_candidate_xy") is not None
        ):
            check.add(path, "path", "unavailable path metrics must be null")
        _budgets(item.get("budgets"), path, check)
        check.flags(item.get("flags"), f"{path}.flags")
        if isinstance(path_id, str):
            result[path_id] = set(joints)
    _sorted_ids(items, "path_id", "$.paths", check)
    return result


def _contacts(
    value: Any, joint_ids: set[str], layers: Mapping[str, tuple[set[int], int]], check: _Check
) -> dict[str, str]:
    result: dict[str, str] = {}
    items = check.array(value, "$.contacts")
    for index, raw in enumerate(items):
        path = f"$.contacts[{index}]"
        item = check.obj(raw, path, {"contact_id", "joint_id", "relation", "layer_ids", "mode",
                     "area", "bbox_xywh", "centroid_xy", "variance_xy", "representative_xy",
                     "error_radius_px", "overlap_ratios", "gap_distance_px", "endpoints_xy", "flags"})
        contact_id, joint_id = item.get("contact_id"), item.get("joint_id")
        if not check.valid_id(contact_id) or contact_id in result:
            check.add(f"{path}.contact_id", "id", "invalid or duplicate contact id")
        if not isinstance(joint_id, str) or joint_id not in joint_ids:
            check.add(f"{path}.joint_id", "unknown_joint", "joint is not in project")
        if item.get("relation") not in _RELATIONS:
            check.add(f"{path}.relation", "enum", "unsupported contact relation")
        layer_pair = item.get("layer_ids")
        if (not isinstance(layer_pair, list) or len(layer_pair) != 2
                or any(not isinstance(value, str) for value in layer_pair) or len(set(layer_pair)) != 2):
            check.add(f"{path}.layer_ids", "shape", "must contain two distinct layer ids")
            layer_pair = []
        for layer_id in layer_pair:
            if layer_id not in layers:
                check.add(f"{path}.layer_ids", "unknown_layer", "layer summary is missing")
        mode, area = item.get("mode"), item.get("area")
        if mode not in {"overlap", "gap"}:
            check.add(f"{path}.mode", "enum", "unsupported contact mode")
        if not _integer(area) or area < 0:
            check.add(f"{path}.area", "bounds", "area must be non-negative")
        check.bbox(item.get("bbox_xywh"), f"{path}.bbox_xywh")
        check.point(item.get("centroid_xy"), f"{path}.centroid_xy")
        check.point(item.get("representative_xy"), f"{path}.representative_xy")
        check.vector(item.get("variance_xy"), f"{path}.variance_xy", 2, maximum=None)
        check.number(item.get("error_radius_px"), f"{path}.error_radius_px")
        ratios = check.vector(item.get("overlap_ratios"), f"{path}.overlap_ratios", 2, maximum=1)
        gap = check.number(item.get("gap_distance_px"), f"{path}.gap_distance_px")
        endpoints = check.points(item.get("endpoints_xy"), f"{path}.endpoints_xy", count=2)
        threshold = 16
        if len(layer_pair) == 2 and all(layer_id in layers for layer_id in layer_pair):
            layer_areas = [layers[layer_id][1] for layer_id in layer_pair]
            threshold = max(16, math.ceil(min(layer_areas) * 0.001))
            if _integer(area) and all(layer_area > 0 for layer_area in layer_areas):
                expected_ratios = [round(area / layer_area, 6) for layer_area in layer_areas]
                if len(ratios) == 2 and any(abs(a - b) > 1e-6 for a, b in zip(ratios, expected_ratios)):
                    check.add(f"{path}.overlap_ratios", "identity", "ratios do not match layer areas")
        if mode == "overlap" and (not _integer(area) or area < threshold or gap != 0):
            check.add(path, "contact", "overlap must have significant area and zero gap")
        if mode == "gap" and (area != 0 or any(ratios) or not _finite(gap) or gap <= 0):
            check.add(path, "contact", "gap must have zero overlap and positive distance")
        if mode == "gap" and len(endpoints) == 2:
            actual = math.dist(endpoints[0], endpoints[1])
            if _finite(gap) and abs(actual - gap) > 1e-6:
                check.add(f"{path}.gap_distance_px", "identity", "does not match endpoints")
        check.flags(item.get("flags"), f"{path}.flags")
        if isinstance(contact_id, str):
            result[contact_id] = joint_id if isinstance(joint_id, str) else ""
    _sorted_ids(items, "contact_id", "$.contacts", check)
    return result


def _observability(
    value: Any, joint_ids: set[str], paths: Mapping[str, set[str]],
    contacts: Mapping[str, str], check: _Check,
) -> None:
    root = check.obj(value, "$.observability", set(joint_ids), required=set())
    seen_paths, seen_contacts = set(), set()
    for joint_id, raw in root.items():
        path = f"$.observability.{joint_id}"
        item = check.obj(raw, path, {"status", "path_ids", "contact_ids", "flags"})
        if item.get("status") not in _OBSERVABILITY:
            check.add(f"{path}.status", "enum", "unsupported observability status")
        path_refs = check.ids(item.get("path_ids"), f"{path}.path_ids")
        contact_refs = check.ids(item.get("contact_ids"), f"{path}.contact_ids")
        if path_refs != sorted(path_refs) or contact_refs != sorted(contact_refs):
            check.add(path, "order", "evidence references must be sorted")
        for ref in path_refs:
            if ref not in paths or joint_id not in paths[ref]:
                check.add(f"{path}.path_ids", "reference", "path does not reference this joint")
        for ref in contact_refs:
            if ref not in contacts or joint_id != contacts[ref]:
                check.add(f"{path}.contact_ids", "reference", "contact does not reference this joint")
        seen_paths.update(path_refs)
        seen_contacts.update(contact_refs)
        check.flags(item.get("flags"), f"{path}.flags")
    if seen_paths != set(paths) or seen_contacts != set(contacts):
        check.add("$.observability", "reference", "every path and contact must be observable")
