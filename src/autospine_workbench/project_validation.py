"""Deterministic validation of an effective workbench project document."""

from __future__ import annotations

from typing import Any, Callable, Mapping, Sequence

from .contracts import VALIDATION_SCHEMA_VERSION, contract_descriptor


AssetResolver = Callable[[str, str, str | None], Any]


def validate_project_document(
    project_id: str,
    project: Mapping[str, Any],
    *,
    revision: int,
    resolve_asset: AssetResolver,
    asset_error_type: type[Exception],
    initial_errors: Sequence[dict[str, str]] = (),
    initial_checks: Sequence[dict[str, Any]] = (),
) -> dict[str, Any]:
    errors = list(initial_errors)
    warnings: list[dict[str, str]] = []
    checks = list(initial_checks)
    width, height = project["canvas"]["width"], project["canvas"]["height"]
    canvas_ok = width > 0 and height > 0
    checks.append({"id": "canvas", "status": "pass" if canvas_ok else "fail"})
    if not canvas_ok:
        errors.append(
            {
                "path": "$.canvas",
                "code": "invalid_canvas",
                "message": "Canvas dimensions must be positive.",
            }
        )

    layers = project["layers"]
    layer_ids = [layer["id"] for layer in layers]
    layers_ok = bool(layer_ids) and len(layer_ids) == len(set(layer_ids))
    checks.append(
        {"id": "layers", "status": "pass" if layers_ok else "fail", "count": len(layer_ids)}
    )
    if not layer_ids:
        errors.append(
            {"path": "$.layers", "code": "missing_layers", "message": "No pixel layers were discovered."}
        )
    elif not layers_ok:
        errors.append(
            {"path": "$.layers", "code": "duplicate_ids", "message": "Layer ids are not unique."}
        )

    missing_assets = 0
    for layer in layers:
        try:
            resolve_asset(project_id, "layer", layer["id"])
        except asset_error_type:
            missing_assets += 1
            errors.append(
                {
                    "path": f"$.layers.{layer['id']}",
                    "code": "missing_asset",
                    "message": "Layer image is missing or unsafe.",
                }
            )
        if layer["empty"]:
            warnings.append(
                {
                    "path": f"$.layers.{layer['id']}",
                    "code": "empty_layer",
                    "message": "Layer has no perceptible alpha and should be excluded or reviewed.",
                }
            )
        if layer["canonical_role"].startswith("unclassified"):
            warnings.append(
                {
                    "path": f"$.layers.{layer['id']}.canonical_role",
                    "code": "unclassified_role",
                    "message": "Layer needs a canonical role override.",
                }
            )
    composite_missing = False
    try:
        resolve_asset(project_id, "composite", None)
    except asset_error_type:
        composite_missing = True
        errors.append(
            {
                "path": "$.assets.composite",
                "code": "missing_asset",
                "message": "Composite image is missing or unsafe.",
            }
        )
    checks.append(
        {
            "id": "assets",
            "status": "fail" if missing_assets or composite_missing else "pass",
            "missing_layer_assets": missing_assets,
        }
    )

    joints = project["skeleton"]["joints"]
    joint_ids = {joint["id"] for joint in joints}
    skeleton_ok = len(joints) == len(joint_ids)
    skeleton_ok = skeleton_ok and all(
        0 <= joint["x"] <= width and 0 <= joint["y"] <= height for joint in joints
    )
    skeleton_ok = skeleton_ok and all(
        bone["start_joint_id"] in joint_ids and bone["end_joint_id"] in joint_ids
        for bone in project["skeleton"]["bones"]
    )
    checks.append(
        {
            "id": "skeleton",
            "status": "pass" if skeleton_ok else "fail",
            "joint_count": len(joints),
            "bone_count": len(project["skeleton"]["bones"]),
        }
    )
    if not skeleton_ok:
        errors.append(
            {
                "path": "$.skeleton",
                "code": "invalid_skeleton",
                "message": "Skeleton ids, endpoints, or bounds are invalid.",
            }
        )
    unresolved_low_confidence = [
        joint
        for joint in joints
        if joint["confidence"] < 0.5 and joint.get("review_state") == "unreviewed"
    ]
    if unresolved_low_confidence:
        warnings.append(
            {
                "path": "$.skeleton.joints",
                "code": "low_confidence_joints",
                "message": f"{len(unresolved_low_confidence)} heuristic joints need review.",
            }
        )

    composite_quality = project["workflow"]["audit_warnings"]["composite_quality"]
    fidelity_status = composite_quality.get("status", "unavailable")
    visible_mae = composite_quality.get("background_matched_rgb_mae")
    raw_mae = float(composite_quality.get("raw_rgba_mae", 0) or 0)
    if fidelity_status == "manual_required":
        warnings.append(
            {
                "path": "$.source.audit",
                "code": "composite_mismatch",
                "message": f"Visible recomposition differs after background matching (RGB MAE {visible_mae:.3f}).",
            }
        )
    elif fidelity_status == "unavailable" and raw_mae > 5:
        warnings.append(
            {
                "path": "$.source.audit",
                "code": "composite_metric_unavailable",
                "message": "Raw RGBA differs, but representation-aware composite metrics are unavailable.",
            }
        )
    checks.append(
        {
            "id": "composite-fidelity",
            "status": "warn" if fidelity_status != "passed" else "pass",
            "metrics": composite_quality,
        }
    )

    status = "invalid" if errors else "needs_review" if warnings else "valid"
    return {
        "schema_version": VALIDATION_SCHEMA_VERSION,
        "contract": contract_descriptor("validation"),
        "project_id": project_id,
        "revision": revision,
        "valid": not errors,
        "status": status,
        "checks": checks,
        "errors": errors,
        "warnings": warnings,
    }
