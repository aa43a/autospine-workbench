"""Generate bounded weighted candidates from exact project inputs, without adoption."""

from copy import deepcopy

from ..asset.joints.mesh_candidate import build_mesh_candidate
from ..asset.joints.mesh_refinement import refine_mesh_weights
from ..benchmark.layer_binding_draft import validate_layer_binding_draft
from ..resolved_project import canonical_sha256
from ..targets.spine43.workbench_preview import build_document, inspect_document
from .animated_motion import build_motion
from .animated_partitions import build_partitions, expand_inputs
from .pipeline_run import PipelineRunError


def review_item(layer, reason, kind="binding"):
    return {"id": (layer or "project") + ":" + reason,
            "layer_id": layer, "type": kind, "risk": "review",
            "reason_code": reason, "authority": "none"}


def prepare_mesh(inputs):
    """Suggestions here are transient preview hypotheses, never saved decisions."""
    draft = deepcopy(inputs.draft)
    suggestions = []
    for record, options in zip(draft["records"], inputs.bindings["bindings"]):
        if record["action"] != "pending":
            continue
        suggested = next((o for o in options["options"]
                          if o["id"] == options.get("suggested_option_id")), None)
        if suggested and suggested["mode"] == "mesh_chain" and len(suggested["bone_ids"]) == 3:
            record.update(action="bind", option_id=suggested["id"],
                          notes="Transient preview hypothesis; original decision remains pending.")
            suggestions.append(record["layer_id"])
    validate_layer_binding_draft(inputs.bindings, draft)
    baseline = build_mesh_candidate(inputs.candidate, inputs.assisted, inputs.skeleton,
                                    inputs.bindings, draft, inputs.images)
    mesh = refine_mesh_weights(baseline, inputs.skeleton, inputs.bindings, draft)
    return {"schema": "autospine.workbench-mesh-stage/v1", "authority": "none",
            "original_draft_sha256": canonical_sha256(inputs.draft),
            "preview_hypothesis_layers": suggestions, "mesh": mesh,
            "partitions": build_partitions(inputs)}


def compile_preview(inputs, mesh_stage, clip):
    expanded = expand_inputs(inputs, mesh_stage.get("partitions", []))
    source = deepcopy(expanded.candidate)
    originals = {r["layer_id"]: r for r in inputs.draft["records"]}
    # Explicit excludes affect this new preview only; historical files remain unchanged.
    source["layers"] = [r for r in source["layers"]
                        if originals[r.get("source_layer_id", r["layer_id"])]["action"] != "exclude"]
    meshes = {r["layer_id"]: r for r in mesh_stage["mesh"]["layers"] if r.get("weights")}
    meshes.update({r["layer_id"]: r for part in mesh_stage.get("partitions", []) for r in part["meshes"]})
    allowed = {"forearm_l", "forearm_r", "calf_l", "calf_r"}
    meshes = {name: row for name, row in meshes.items()
              if len(row["weights"][0]) == 1 or row["weights"][0][1]["bone_id"] in allowed}
    rigid = {}
    for record, binding in zip(inputs.draft["records"], inputs.bindings["bindings"]):
        option = next((o for o in binding["options"] if o["id"] == record["option_id"]), None)
        if record["action"] == "bind" and option and option["mode"] == "rigid":
            rigid[record["layer_id"]] = option["bone_ids"][0]
    joints = sorted({row["weights"][0][1]["bone_id"] for row in meshes.values() if len(row["weights"][0]) > 1})
    motion = build_motion(clip, joints)
    doc, regions, context, setup_error = build_document(source, inputs.skeleton, meshes, motion, rigid)
    if not doc["slots"]:
        raise PipelineRunError("animated_no_visible_layers")
    qa = inspect_document(doc)
    failed = [name for name in meshes if not qa["regions"][name]["passed"]]
    # Geometry-failed candidates remain visible as rigid context, never moving meshes.
    if failed:
        meshes = {name: row for name, row in meshes.items() if name not in failed}
        motion = build_motion(clip, sorted({r["weights"][0][1]["bone_id"] for r in meshes.values()
                                           if len(r["weights"][0]) > 1}))
        doc, regions, context, setup_error = build_document(source, inputs.skeleton, meshes, motion, rigid)
        qa = inspect_document(doc)
    items = []
    for row in mesh_stage["mesh"]["layers"]:
        name = row["layer_id"]
        if originals[name]["action"] == "exclude":
            continue
        if name in meshes:
            items.append(review_item(name, "mesh_review_required", "mesh"))
        elif name in failed:
            items.append(review_item(name, "animated_geometry_failed", "mesh"))
        elif name in context and name not in rigid:
            reasons = row.get("reason_codes") or ["rigid_context_unreviewed"]
            items.extend(review_item(name, reason) for reason in reasons)
    items.append(review_item(None, "cross_layer_seam_review_required", "seam"))
    items.append(review_item(None, "runtime_visual_review_required", "runtime"))
    for part in mesh_stage.get("partitions", []):
        items.append(review_item(part["source_layer_id"], "partition_assignment_review_required", "partition"))
        if part["qa"]["visible_pixel_counts"]["3"]:
            items.append(review_item(part["source_layer_id"], "residual_binding_required", "partition"))
    if not meshes:
        items.append(review_item(None, "animated_no_eligible_mesh", "mesh"))
    return {"document": doc, "regions": regions, "motion": motion, "expanded_inputs": expanded,
            "review_items": items,
            "summary": {"mesh_layers": len(meshes), "context_layers": len(context),
                        "visible_layers": len(regions), "bone_count": len(doc["bones"]),
                        "rejected_mesh_layers": failed,
                        "partition_source_layers": len(mesh_stage.get("partitions", [])),
                        "preview_hypothesis_layers": mesh_stage["preview_hypothesis_layers"]},
            "qa": {"geometry": qa, "setup_max_error_px": setup_error,
                   "runtime_status": "not_run", "seam_status": "needs_review",
                   "alpha_coverage": "alpha_grid_threshold_8_not_full_rgba_proof",
                   "full_character_animation": False, "authority": "none"}}
