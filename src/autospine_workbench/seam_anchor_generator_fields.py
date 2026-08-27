"""Canonical field builder for the P10.5a generator identity."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from .resolved_project import canonical_sha256


def build_candidate_generator(values: Mapping[str, Any]) -> dict[str, Any]:
    """Build one sealed profile from explicit runtime-consumer bindings."""

    algorithm = {
        "input_admission": deepcopy(values["input_admission"]),
        "alpha": {
            "threshold": values["alpha_threshold"],
            "max_total_runs": values["max_total_runs"],
            "max_runs_per_mask_by_consumer": {
                "alpha_cache": values["alpha_cache_max_runs"],
                "candidate_geometry": values["geometry_max_runs"],
                "lobe_isolation": values["lobe_max_runs"],
                "sampler": values["sampling_max_runs"],
            },
        },
        "contact": {
            "candidate_max_gap_px": values["candidate_max_gap"],
            "contact_api_max_gap_px": values["contact_api_max_gap"],
            "connectivity": values["contact_connectivity"],
            "minimum_lobe_area_px": values["min_lobe_area"],
            "minimum_lobe_ratio": values["min_lobe_ratio"],
            "lobe_connectivity": values["lobe_connectivity"],
            "lobe_identity": values["lobe_identity"],
        },
        "relationships": {
            "rows": [{
                "relation": relation, "parent_role": parent,
                "child_role": child, "joint": joint,
            } for relation, parent, child, joint
                in values["contact_relations"]],
            "sides": list(values["sides"]),
            "role_token_rows": [{
                "role": role, "tokens": list(tokens),
            } for role, tokens in values["role_tokens"]],
            "parent_neutral_relations": sorted(values["neutral_relations"]),
            "neutral_sides": sorted(values["neutral_sides"]),
            "supported_attachment_types": sorted(values["supported_types"]),
            "max_candidate_pairs_by_consumer": {
                "inventory": values["relations_max_pairs"],
                "candidate_geometry": values["geometry_max_pairs"],
            },
        },
        "limits": {
            "max_options_per_relationship": values["max_options"],
            "max_total_options": values["max_total_options"],
            "max_lobe_intersection_runs": values["lobe_max_intersections"],
            "max_sampling_intersection_runs": (
                values["sampling_max_intersections"]
            ),
            "max_common_alpha_pixels": values["max_common_pixels"],
            "max_document_bytes": values["max_document_bytes"],
        },
        "sampling": {
            "profile_by_consumer": {
                "sampler": values["sampling_profile"],
                "candidate_policy": values["policy_sampling_profile"],
            },
            "requested_anchor_pairs_by_consumer": {
                "candidate_geometry": values["geometry_requested_pairs"],
                "sampler_default": values["sampling_default_pairs"],
                "candidate_policy_max": values["policy_candidate_max"],
            },
            "sampler_pair_range": [
                values["sampling_min_pairs"], values["sampling_max_pairs"],
            ],
            "pair_validation_range": [
                values["pair_min"], values["pair_max"],
            ],
            "max_abs_canvas_coordinate": values["max_canvas_coordinate"],
        },
        "locators": {
            "region_quantization": values["region_quantization"],
            "mesh_quantization": values["mesh_quantization"],
            "max_mesh_vertices": values["max_mesh_vertices"],
            "max_mesh_triangles": values["max_mesh_triangles"],
            "max_abs_attachment_coordinate": values["max_coordinate"],
            "mesh_shared_edge_policy": values["mesh_shared_edge_policy"],
        },
        "pair_policy": {
            "supported_types": list(values["supported_pairs"]),
            "mesh_mesh": values["mesh_mesh_policy"],
            "order": values["pair_order_policy"],
            "connector_intersection": values["intersection_policy"],
        },
        "reason_policy": {
            "relationship_codes": sorted(values["relationship_reasons"]),
            "relationship_absence_codes": sorted(
                values["absence_reasons"]
            ),
            "option_codes": sorted(values["option_reasons"]),
            "no_contact_codes": sorted(values["no_contact_reasons"]),
            "overlap_unavailable_codes": sorted(
                values["overlap_unavailable_reasons"]
            ),
            "gap_unavailable_codes": sorted(values["gap_reasons"]),
            "relationship_option_diagnostics": "exact_set_equality",
        },
    }
    return {
        "id": "static-seam-anchor-candidate-compiler",
        "version": "1.1.0",
        "algorithm_profile_sha256": canonical_sha256(algorithm),
        "algorithm_profile": algorithm,
    }
