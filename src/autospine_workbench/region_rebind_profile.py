"""Pinned semantics for authority-free sampled region rebind candidates."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .resolved_project import canonical_sha256


FORMAT = "autospine-region-rebind-candidates"
FORMAT_VERSION = 1
MAX_CANDIDATE_BONES = 16
MAX_MOTION_SAMPLES = 65536
MAX_RIG_ENTITIES = 4096
NUMERIC_PRECISION_DECIMALS = 9
MIN_RELATIVE_MOTION_IMPROVEMENT = 0.05
RANK_TIE_RELATIVE_TOLERANCE = 0.01
SETUP_RECONSTRUCTION_TOLERANCE_PX = 1e-7


_ANALYZER: dict[str, Any] = {
    "id": "sampled-region-rebind-analyzer",
    "version": "1.0.0",
    "config": {
        "geometry_source": "region-corner-envelope",
        "default_candidate_scope": "current-direct-parent-and-children",
        "explicit_candidate_scope": "one-hop-same-chain-only",
        "sample_pose_space": "setup-local-bone-rotation-plus-root-translation",
        "motion_metric": "root-compensated-corner-displacement",
        "recommendation_ranking": [
            "setup-subtree-segment-coverage-descending",
            "root-compensated-centroid-rms",
            "root-compensated-maximum-vertex-motion",
            "viewport-overflow-sample-count-diagnostic",
            "viewport-maximum-overflow-diagnostic",
            "bone-id",
        ],
        "minimum_relative_motion_improvement": MIN_RELATIVE_MOTION_IMPROVEMENT,
        "rank_tie_relative_tolerance": RANK_TIE_RELATIVE_TOLERANCE,
        "setup_reconstruction_tolerance_px": SETUP_RECONSTRUCTION_TOLERANCE_PX,
        "numeric_precision_decimals": NUMERIC_PRECISION_DECIMALS,
        "viewport_policy": "diagnostic-only-free-camera-compatible",
        "recommendation_gate": (
            "one-hop-parent-with-increased-region-envelope-chain-coverage-"
            "and-motion-improvement"
        ),
    },
}


_SEMANTICS: dict[str, Any] = {
    "scope": "sampled-region-rebind-candidate-only",
    "authority": "none",
    "human_decision_emitted": False,
    "override_written": False,
    "automatic_application_performed": False,
    "setup_reconstruction_claimed": True,
    "sampled_motion_evidence_claimed": True,
    "geometry_basis": "region-corner-envelope-not-alpha-visible-pixels",
    "viewport_overflow_is_correctness_gate": False,
    "continuous_time_safety_claimed": False,
    "visual_quality_claimed": False,
    "seam_safety_claimed": False,
    "release_authority": False,
}


def region_rebind_analyzer_profile() -> dict[str, Any]:
    """Return a detached copy of the pinned analyzer profile."""

    return deepcopy(_ANALYZER)


def region_rebind_analyzer_profile_sha256() -> str:
    """Return the canonical identity of the complete analyzer semantics."""

    return canonical_sha256(_ANALYZER)


def region_rebind_semantics() -> dict[str, Any]:
    """Return the fixed zero-authority claims."""

    return deepcopy(_SEMANTICS)
