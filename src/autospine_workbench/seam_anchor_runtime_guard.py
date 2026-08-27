"""Fail-closed consistency checks for P10.5a runtime policy aliases."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any


class SeamAnchorRuntimeProfileError(ValueError):
    """Raised when an imported policy alias diverges from its authority."""


def require_candidate_runtime_consistency() -> None:
    """Reject partially updated policy constants before hashing or compiling."""

    from . import seam_anchor_alpha_cache as alpha
    from . import seam_anchor_candidate_fields as fields
    from . import seam_anchor_candidate_geometry as geometry
    from . import seam_anchor_candidate_policy as policy
    from . import seam_anchor_candidate_profile as candidate_profile
    from . import seam_anchor_candidate_validation as validation
    from . import seam_anchor_candidates as compiler
    from . import seam_anchor_lobes as lobes
    from . import seam_anchor_locators as locators
    from . import seam_anchor_pair_validation as pairs
    from . import seam_anchor_relations as relations
    from . import seam_anchor_sampling as sampling
    from . import seam_anchor_profile as input_profile

    checks = (
        ("alpha.threshold", alpha.ALPHA_THRESHOLD,
         candidate_profile.ALPHA_THRESHOLD),
        ("alpha.total_runs", alpha.MAX_TOTAL_ALPHA_RUNS,
         candidate_profile.MAX_TOTAL_ALPHA_RUNS),
        ("alpha.mask_runs", alpha.MAX_RUNS_PER_MASK,
         sampling.MAX_RUNS_PER_MASK),
        ("geometry.mask_runs", geometry.MAX_RUNS_PER_MASK,
         sampling.MAX_RUNS_PER_MASK),
        ("geometry.anchor_pairs", geometry.DEFAULT_ANCHOR_PAIRS,
         sampling.DEFAULT_ANCHOR_PAIRS),
        ("geometry.contact_gap", geometry.CONTACT_MAX_GAP_PX,
         candidate_profile.CONTACT_MAX_GAP_PX),
        ("geometry.relation_pairs", geometry.MAX_RELATION_CANDIDATE_PAIRS,
         input_profile.MAX_RELATION_CANDIDATE_PAIRS),
        ("geometry.options", geometry.MAX_OPTIONS_PER_RELATION,
         candidate_profile.MAX_OPTIONS_PER_RELATION),
        ("geometry.total_options", geometry.MAX_TOTAL_OPTIONS,
         candidate_profile.MAX_TOTAL_OPTIONS),
        ("lobes.mask_runs", lobes.MAX_RUNS_PER_MASK,
         sampling.MAX_RUNS_PER_MASK),
        ("lobes.intersection_runs", lobes.MAX_INTERSECTION_RUNS,
         sampling.MAX_INTERSECTION_RUNS),
        ("policy.minimum_pairs", policy.MIN_ANCHOR_PAIRS,
         sampling.MIN_ANCHOR_PAIRS),
        ("policy.maximum_pairs", policy.DEFAULT_ANCHOR_PAIRS,
         sampling.DEFAULT_ANCHOR_PAIRS),
        ("policy.sampling_profile", policy.SAMPLING_PROFILE,
         sampling.SAMPLING_PROFILE),
        ("sampling.minimum_pairs", sampling.MIN_ANCHOR_PAIRS,
         pairs.MIN_ANCHOR_PAIRS),
        ("sampling.maximum_pairs", sampling.MAX_ANCHOR_PAIRS,
         pairs.MAX_ANCHOR_PAIRS),
        ("relations.pair_limit", relations.MAX_RELATION_CANDIDATE_PAIRS,
         input_profile.MAX_RELATION_CANDIDATE_PAIRS),
        ("validation.document_bytes", validation.MAX_DOCUMENT_BYTES,
         candidate_profile.MAX_DOCUMENT_BYTES),
        ("validation.options", validation.MAX_OPTIONS_PER_RELATION,
         candidate_profile.MAX_OPTIONS_PER_RELATION),
        ("validation.total_options", validation.MAX_TOTAL_OPTIONS,
         candidate_profile.MAX_TOTAL_OPTIONS),
        ("validation.anchor_pairs", validation.MAX_ANCHOR_PAIRS,
         pairs.MAX_ANCHOR_PAIRS),
        ("validation.contact_gap", validation.CONTACT_MAX_GAP_PX,
         candidate_profile.CONTACT_MAX_GAP_PX),
        ("validation.relationships", validation.RELATIONSHIP_PROFILE,
         candidate_profile.RELATIONSHIP_PROFILE),
        ("validation.format", validation.FORMAT,
         candidate_profile.FORMAT),
        ("validation.format_version", validation.FORMAT_VERSION,
         candidate_profile.FORMAT_VERSION),
        ("validation.semantics", validation.SEMANTICS,
         candidate_profile.SEMANTICS),
        ("validation.claims", validation.CLAIMS,
         candidate_profile.CLAIMS),
        ("validation.release_gate", validation.RELEASE_GATE,
         candidate_profile.RELEASE_GATE),
        ("validation.source_fields", validation.SEAM_SOURCE_IDENTITY_FIELDS,
         input_profile.SEAM_SOURCE_IDENTITY_FIELDS),
        ("compiler.format", compiler.FORMAT,
         candidate_profile.FORMAT),
        ("compiler.format_version", compiler.FORMAT_VERSION,
         candidate_profile.FORMAT_VERSION),
        ("compiler.semantics", compiler.SEMANTICS,
         candidate_profile.SEMANTICS),
        ("compiler.claims", compiler.CLAIMS,
         candidate_profile.CLAIMS),
        ("compiler.release_gate", compiler.RELEASE_GATE,
         candidate_profile.RELEASE_GATE),
        ("fields.region_quantization", fields.REGION_QUANTIZATION,
         locators.REGION_QUANTIZATION),
        ("fields.mesh_quantization", fields.MESH_QUANTIZATION,
         locators.MESH_QUANTIZATION),
        ("fields.mesh_vertices", fields.MAX_MESH_VERTICES,
         locators.MAX_MESH_VERTICES),
        ("fields.mesh_triangles", fields.MAX_MESH_TRIANGLES,
         locators.MAX_MESH_TRIANGLES),
        ("fields.coordinate", fields.MAX_ABS_ATTACHMENT_COORDINATE,
         locators.MAX_ABS_ATTACHMENT_COORDINATE),
        ("fields.image_pixels", fields.MAX_ATTACHMENT_PIXELS,
         input_profile.MAX_ATTACHMENT_PIXELS),
    )
    for name, actual, expected in checks:
        if not _same(actual, expected):
            raise SeamAnchorRuntimeProfileError(
                f"Static seam runtime policy alias diverged: {name}"
            )
    if policy.ALL_REASON_CODES != (
        policy.RELATIONSHIP_REASON_CODES | policy.OPTION_REASON_CODES
    ) or policy.OPTION_REASON_CODES != (
        policy.NO_CONTACT_REASON_CODES
        | policy.OVERLAP_UNAVAILABLE_REASON_CODES
        | policy.GAP_UNAVAILABLE_REASON_CODES
    ) or not policy.ABSENCE_REASON_CODES <= policy.RELATIONSHIP_REASON_CODES:
        raise SeamAnchorRuntimeProfileError(
            "Static seam reason-policy aliases are inconsistent"
        )
    _require_role_token_rows(relations.ROLE_TOKEN_PROFILE)
    expected_sides = frozenset({
        *relations.SIDES, *relations._NEUTRAL_SIDES,
    })
    if relations._VALID_SIDES != expected_sides:
        raise SeamAnchorRuntimeProfileError(
            "Static seam runtime policy alias diverged: relations.valid_sides"
        )


def _same(actual: Any, expected: Any) -> bool:
    return type(actual) is type(expected) and actual == expected


def _require_role_token_rows(rows: Sequence[Any]) -> None:
    roles = []
    for row in rows:
        if not isinstance(row, tuple) or len(row) != 2:
            raise SeamAnchorRuntimeProfileError(
                "Static seam role-token profile is invalid"
            )
        role, tokens = row
        if not isinstance(role, str) or not isinstance(tokens, tuple) \
                or not tokens or len(tokens) != len(set(tokens)) \
                or any(not isinstance(token, str) or not token
                       for token in tokens):
            raise SeamAnchorRuntimeProfileError(
                "Static seam role-token profile is invalid"
            )
        roles.append(role)
    if len(roles) != len(set(roles)):
        raise SeamAnchorRuntimeProfileError(
            "Static seam role-token profile contains duplicate roles"
        )
