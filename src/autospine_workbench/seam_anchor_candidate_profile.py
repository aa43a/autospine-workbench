"""Pinned P10.5a static seam-candidate policy and hash domains."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .contact_geometry import (
    CONTACT_CONNECTIVITY,
    MAX_GAP_PX,
    MIN_CONTACT_LOBE_AREA,
    MIN_CONTACT_LOBE_RATIO,
)
from .limb_contact_roles import CONTACT_RELATIONS, SIDES
from .resolved_project import canonical_sha256
from .seam_anchor_candidate_policy import (
    ABSENCE_REASON_CODES,
    GAP_UNAVAILABLE_REASON_CODES,
    NO_CONTACT_REASON_CODES,
    OPTION_REASON_CODES,
    OVERLAP_UNAVAILABLE_REASON_CODES,
    RELATIONSHIP_REASON_CODES,
)
from .seam_anchor_generator_fields import build_candidate_generator
from .seam_anchor_locators import (
    MAX_ABS_ATTACHMENT_COORDINATE,
    MAX_MESH_TRIANGLES,
    MAX_MESH_VERTICES,
    MESH_QUANTIZATION,
    MESH_SHARED_EDGE_POLICY,
    REGION_QUANTIZATION,
)
from .seam_anchor_pair_validation import (
    CONNECTOR_INTERSECTION_POLICY,
    MAX_ANCHOR_PAIRS,
    MIN_ANCHOR_PAIRS,
    PAIR_ORDER_POLICY,
)
from .seam_anchor_relation_pairs import (
    MESH_MESH_POLICY,
    SUPPORTED_ATTACHMENT_PAIRS,
)
from .seam_anchor_relations import (
    PARENT_NEUTRAL_RELATIONS,
    ROLE_TOKEN_PROFILE,
    _NEUTRAL_SIDES,
    _SUPPORTED_TYPES,
)
from .seam_anchor_lobes import LOBE_CONNECTIVITY, LOBE_IDENTITY_PROFILE
from .seam_anchor_sampling import (
    DEFAULT_ANCHOR_PAIRS,
    MAX_ABS_CANVAS_COORDINATE,
    MAX_COMMON_ALPHA_PIXELS,
    MAX_INTERSECTION_RUNS,
    MAX_RUNS_PER_MASK,
    SAMPLING_PROFILE,
)
from .seam_anchor_profile import (
    MAX_RELATION_CANDIDATE_PAIRS,
    seam_anchor_resource_limits,
)
from .seam_anchor_runtime_guard import require_candidate_runtime_consistency


FORMAT = "autospine-seam-anchor-candidates"
FORMAT_VERSION = 1
ALPHA_THRESHOLD = 8
CONTACT_MAX_GAP_PX = 8.0
MAX_OPTIONS_PER_RELATION = 64
MAX_TOTAL_OPTIONS = 384
MAX_TOTAL_ALPHA_RUNS = 262_144
MAX_DOCUMENT_BYTES = 64 * 1024 * 1024

RELATIONSHIP_PROFILE = tuple(
    (f"seam.{relation}.{side}", relation, f"{joint}.{side}", side)
    for relation, _parent, _child, joint in CONTACT_RELATIONS
    for side in SIDES
)

OPTION_EVIDENCE_HASH_DOMAIN = (
    "autospine-seam-anchor-option-evidence/v1"
)
RELATIONSHIP_EVIDENCE_HASH_DOMAIN = (
    "autospine-seam-anchor-relationship-evidence/v1"
)


def _values() -> dict[str, Any]:
    return {
        "input_admission": seam_anchor_resource_limits(),
        "alpha_threshold": ALPHA_THRESHOLD,
        "alpha_cache_max_runs": MAX_RUNS_PER_MASK,
        "geometry_max_runs": MAX_RUNS_PER_MASK,
        "lobe_max_runs": MAX_RUNS_PER_MASK,
        "sampling_max_runs": MAX_RUNS_PER_MASK,
        "max_total_runs": MAX_TOTAL_ALPHA_RUNS,
        "candidate_max_gap": CONTACT_MAX_GAP_PX,
        "contact_api_max_gap": MAX_GAP_PX,
        "contact_connectivity": CONTACT_CONNECTIVITY,
        "min_lobe_area": MIN_CONTACT_LOBE_AREA,
        "min_lobe_ratio": MIN_CONTACT_LOBE_RATIO,
        "lobe_connectivity": LOBE_CONNECTIVITY,
        "lobe_identity": LOBE_IDENTITY_PROFILE,
        "contact_relations": CONTACT_RELATIONS, "sides": SIDES,
        "neutral_relations": PARENT_NEUTRAL_RELATIONS,
        "role_tokens": ROLE_TOKEN_PROFILE,
        "supported_pairs": SUPPORTED_ATTACHMENT_PAIRS,
        "mesh_mesh_policy": MESH_MESH_POLICY,
        "relations_max_pairs": MAX_RELATION_CANDIDATE_PAIRS,
        "geometry_max_pairs": MAX_RELATION_CANDIDATE_PAIRS,
        "neutral_sides": _NEUTRAL_SIDES, "supported_types": _SUPPORTED_TYPES,
        "max_options": MAX_OPTIONS_PER_RELATION,
        "max_total_options": MAX_TOTAL_OPTIONS,
        "lobe_max_intersections": MAX_INTERSECTION_RUNS,
        "sampling_max_intersections": MAX_INTERSECTION_RUNS,
        "max_common_pixels": MAX_COMMON_ALPHA_PIXELS,
        "max_document_bytes": MAX_DOCUMENT_BYTES,
        "sampling_profile": SAMPLING_PROFILE,
        "policy_sampling_profile": SAMPLING_PROFILE,
        "geometry_requested_pairs": DEFAULT_ANCHOR_PAIRS,
        "sampling_default_pairs": DEFAULT_ANCHOR_PAIRS,
        "policy_candidate_max": DEFAULT_ANCHOR_PAIRS,
        "sampling_min_pairs": MIN_ANCHOR_PAIRS,
        "sampling_max_pairs": MAX_ANCHOR_PAIRS,
        "pair_min": MIN_ANCHOR_PAIRS, "pair_max": MAX_ANCHOR_PAIRS,
        "max_canvas_coordinate": MAX_ABS_CANVAS_COORDINATE,
        "region_quantization": REGION_QUANTIZATION,
        "mesh_quantization": MESH_QUANTIZATION,
        "max_mesh_vertices": MAX_MESH_VERTICES,
        "max_mesh_triangles": MAX_MESH_TRIANGLES,
        "max_coordinate": MAX_ABS_ATTACHMENT_COORDINATE,
        "mesh_shared_edge_policy": MESH_SHARED_EDGE_POLICY,
        "pair_order_policy": PAIR_ORDER_POLICY,
        "intersection_policy": CONNECTOR_INTERSECTION_POLICY,
        "relationship_reasons": RELATIONSHIP_REASON_CODES,
        "absence_reasons": ABSENCE_REASON_CODES,
        "option_reasons": OPTION_REASON_CODES,
        "no_contact_reasons": NO_CONTACT_REASON_CODES,
        "overlap_unavailable_reasons": OVERLAP_UNAVAILABLE_REASON_CODES,
        "gap_reasons": GAP_UNAVAILABLE_REASON_CODES,
    }


GENERATOR = build_candidate_generator(_values())


def candidate_generator_profile() -> dict[str, Any]:
    """Snapshot actual imported behavior constants into candidate identity."""

    require_candidate_runtime_consistency()

    from . import seam_anchor_alpha_cache as alpha
    from . import seam_anchor_candidate_geometry as geometry
    from . import contact_geometry as contact
    from . import seam_anchor_locators as locators
    from . import seam_anchor_lobes as lobes
    from . import seam_anchor_pair_validation as pairs
    from . import seam_anchor_candidate_policy as policy
    from . import seam_anchor_relation_pairs as relation_pairs
    from . import seam_anchor_relations as relations
    from . import seam_anchor_sampling as sampling
    from . import seam_anchor_profile as input_profile

    values = {
        "input_admission": input_profile.seam_anchor_resource_limits(),
        "alpha_threshold": alpha.ALPHA_THRESHOLD,
        "alpha_cache_max_runs": alpha.MAX_RUNS_PER_MASK,
        "geometry_max_runs": geometry.MAX_RUNS_PER_MASK,
        "lobe_max_runs": lobes.MAX_RUNS_PER_MASK,
        "sampling_max_runs": sampling.MAX_RUNS_PER_MASK,
        "max_total_runs": alpha.MAX_TOTAL_ALPHA_RUNS,
        "candidate_max_gap": geometry.CONTACT_MAX_GAP_PX,
        "contact_api_max_gap": contact.MAX_GAP_PX,
        "contact_connectivity": contact.CONTACT_CONNECTIVITY,
        "min_lobe_area": contact.MIN_CONTACT_LOBE_AREA,
        "min_lobe_ratio": contact.MIN_CONTACT_LOBE_RATIO,
        "lobe_connectivity": lobes.LOBE_CONNECTIVITY,
        "lobe_identity": lobes.LOBE_IDENTITY_PROFILE,
        "contact_relations": relations.CONTACT_RELATIONS,
        "sides": relations.SIDES,
        "neutral_relations": relations.PARENT_NEUTRAL_RELATIONS,
        "role_tokens": relations.ROLE_TOKEN_PROFILE,
        "supported_pairs": relation_pairs.SUPPORTED_ATTACHMENT_PAIRS,
        "mesh_mesh_policy": relation_pairs.MESH_MESH_POLICY,
        "relations_max_pairs": relations.MAX_RELATION_CANDIDATE_PAIRS,
        "geometry_max_pairs": geometry.MAX_RELATION_CANDIDATE_PAIRS,
        "neutral_sides": relations._NEUTRAL_SIDES,
        "supported_types": relations._SUPPORTED_TYPES,
        "max_options": geometry.MAX_OPTIONS_PER_RELATION,
        "max_total_options": geometry.MAX_TOTAL_OPTIONS,
        "lobe_max_intersections": lobes.MAX_INTERSECTION_RUNS,
        "sampling_max_intersections": sampling.MAX_INTERSECTION_RUNS,
        "max_common_pixels": sampling.MAX_COMMON_ALPHA_PIXELS,
        "max_document_bytes": MAX_DOCUMENT_BYTES,
        "sampling_profile": sampling.SAMPLING_PROFILE,
        "policy_sampling_profile": policy.SAMPLING_PROFILE,
        "geometry_requested_pairs": geometry.DEFAULT_ANCHOR_PAIRS,
        "sampling_default_pairs": sampling.DEFAULT_ANCHOR_PAIRS,
        "policy_candidate_max": policy.DEFAULT_ANCHOR_PAIRS,
        "sampling_min_pairs": sampling.MIN_ANCHOR_PAIRS,
        "sampling_max_pairs": sampling.MAX_ANCHOR_PAIRS,
        "pair_min": pairs.MIN_ANCHOR_PAIRS,
        "pair_max": pairs.MAX_ANCHOR_PAIRS,
        "max_canvas_coordinate": sampling.MAX_ABS_CANVAS_COORDINATE,
        "region_quantization": locators.REGION_QUANTIZATION,
        "mesh_quantization": locators.MESH_QUANTIZATION,
        "max_mesh_vertices": locators.MAX_MESH_VERTICES,
        "max_mesh_triangles": locators.MAX_MESH_TRIANGLES,
        "max_coordinate": locators.MAX_ABS_ATTACHMENT_COORDINATE,
        "mesh_shared_edge_policy": locators.MESH_SHARED_EDGE_POLICY,
        "pair_order_policy": pairs.PAIR_ORDER_POLICY,
        "intersection_policy": pairs.CONNECTOR_INTERSECTION_POLICY,
        "relationship_reasons": policy.RELATIONSHIP_REASON_CODES,
        "absence_reasons": policy.ABSENCE_REASON_CODES,
        "option_reasons": policy.OPTION_REASON_CODES,
        "no_contact_reasons": policy.NO_CONTACT_REASON_CODES,
        "overlap_unavailable_reasons": (
            policy.OVERLAP_UNAVAILABLE_REASON_CODES
        ),
        "gap_reasons": policy.GAP_UNAVAILABLE_REASON_CODES,
    }
    return build_candidate_generator(values)

SEMANTICS = {
    "mode": "candidate_only",
    "coordinate_space": "setup_canvas_top_left_y_down_pixels",
    "locator_space": "attachment_local",
    "human_decision_emitted": False,
    "motion_or_clip_input_admitted": False,
    "automatic_fallback_locator_emitted": False,
    "gap_locator_emitted": False,
}

CLAIMS = {
    "exact_static_source_admitted": True,
    "semantic_relationships_compiled": True,
    "static_locator_candidates_compiled": True,
    "human_static_locator_selection_recorded": False,
    "reviewed_seam_anchor_set": False,
    "dynamic_seam_safety": False,
    "visual_seam_quality": False,
    "runtime_equivalence": False,
    "publishable_timeline": False,
    "release_authority": False,
}

RELEASE_GATE = {
    "status": "blocked",
    "reasons": [
        "dynamic_seam_safety_unproven",
        "human_seam_anchor_decision_missing",
        "reviewed_seam_anchor_set_missing",
        "runtime_equivalence_unproven",
        "visual_seam_quality_unproven",
    ],
}


def option_evidence_sha256(payload: Mapping[str, Any]) -> str:
    """Seal one complete option payload before its digest field is added."""

    return canonical_sha256({
        "domain": OPTION_EVIDENCE_HASH_DOMAIN,
        "option": dict(payload),
    })


def relationship_evidence_sha256(payload: Mapping[str, Any]) -> str:
    """Seal one complete relationship payload before its digest is added."""

    return canonical_sha256({
        "domain": RELATIONSHIP_EVIDENCE_HASH_DOMAIN,
        "relationship": dict(payload),
    })
