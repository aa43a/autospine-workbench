"""Explicit-address upstream reader for P10.5d v2 compilation."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .manifest_artifacts import LayerManifestError, require_safe_token, require_sha256
from .p10_safety_analysis_job_store_v2 import (
    P10SafetyAnalysisJobStoreV2,
    P10SafetyAnalysisJobStoreV2Error,
)
from .resolved_project import canonical_sha256
from .reviewed_seam_anchor_set_bundle_reader import (
    VerifiedReviewedSeamAnchorSetBundle,
    VerifiedReviewedSeamAnchorSetBundleReader,
    VerifiedReviewedSeamAnchorSetBundleReaderError,
)
from .seam_anchor_review_json import canonical_json_copy


class P10DynamicSeamInputsV2Error(RuntimeError):
    """Raised when an explicitly addressed upstream artifact differs."""


@dataclass(frozen=True, slots=True)
class P10DynamicSeamInputsV2:
    project_id: str
    safety_run_id: str
    continuous_proof_sha256: str
    reviewed_set_sha256: str
    reviewed_set_bundle_sha256: str
    _continuous_proof: dict = field(repr=False)
    _reviewed_bundle: VerifiedReviewedSeamAnchorSetBundle = field(repr=False)

    @property
    def continuous_proof(self) -> dict:
        return canonical_json_copy(self._continuous_proof)

    @property
    def reviewed_bundle(self) -> VerifiedReviewedSeamAnchorSetBundle:
        return self._reviewed_bundle


def load_p10_dynamic_seam_inputs_v2(
    state_root: Path,
    project_id: str,
    safety_run_id: str,
    *,
    continuous_proof_sha256: str,
    reviewed_set_sha256: str,
    reviewed_set_bundle_sha256: str,
) -> P10DynamicSeamInputsV2:
    """Load only the supplied P10.4b-v2 and P10.5c-v1 addresses."""

    try:
        project = require_safe_token(project_id, "Dynamic seam v2 project")
        run_id = require_sha256(safety_run_id, "P10.4b v2 run")
        continuous_sha = require_sha256(
            continuous_proof_sha256, "P10.4b v2 continuous proof",
        )
        set_sha = require_sha256(
            reviewed_set_sha256, "Reviewed seam-anchor set v1",
        )
        bundle_sha = require_sha256(
            reviewed_set_bundle_sha256,
            "Reviewed seam-anchor set v1 bundle",
        )
        safety = P10SafetyAnalysisJobStoreV2(Path(state_root))
        snapshot = safety.load(run_id)
        head = snapshot.events[-1].document if snapshot.events else {}
        if snapshot.status != "completed" \
                or head.get("result", {}).get("continuous_sha256") \
                    != continuous_sha:
            raise P10DynamicSeamInputsV2Error(
                "P10.4b v2 run differs from explicit continuous address"
            )
        _amplitude, continuous = safety.read_result(run_id)
        if canonical_sha256(continuous) != continuous_sha \
                or continuous.get("project_id") != project:
            raise P10DynamicSeamInputsV2Error(
                "P10.4b v2 exact proof differs from requested project"
            )
        reviewed = VerifiedReviewedSeamAnchorSetBundleReader(
            Path(state_root)
        ).load(project, set_sha, bundle_sha)
        if reviewed.project_id != project \
                or reviewed.set_sha256 != set_sha \
                or reviewed.bundle_sha256 != bundle_sha:
            raise P10DynamicSeamInputsV2Error(
                "P10.5c v1 bundle differs from explicit address"
            )
        return P10DynamicSeamInputsV2(
            project, run_id, continuous_sha, set_sha, bundle_sha,
            canonical_json_copy(continuous), reviewed,
        )
    except P10DynamicSeamInputsV2Error:
        raise
    except (
        AttributeError, KeyError, LayerManifestError, OSError,
        OverflowError, P10SafetyAnalysisJobStoreV2Error,
        RecursionError, RuntimeError, TypeError, UnicodeError, ValueError,
        VerifiedReviewedSeamAnchorSetBundleReaderError,
    ) as exc:
        raise P10DynamicSeamInputsV2Error(
            "P10.5d v2 exact upstream load failed"
        ) from exc


__all__ = [
    "P10DynamicSeamInputsV2", "P10DynamicSeamInputsV2Error",
    "load_p10_dynamic_seam_inputs_v2",
]
