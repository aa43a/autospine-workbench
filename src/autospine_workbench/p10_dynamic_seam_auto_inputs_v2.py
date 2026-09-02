"""Automatic current-authority closure for the P10.5d v2 job API."""

from __future__ import annotations

from dataclasses import dataclass

from .body_sway_dynamic_seam_profile_v2 import (
    FORMAT as SOURCE_FORMAT, FORMAT_VERSION as SOURCE_VERSION,
)
from .body_sway_dynamic_seam_bundle_contract_v2 import DOCUMENT_NAMES
from .motion_policy_seam_review_entry import (
    MANUAL_REVIEW_REQUIRED, build_motion_policy_seam_review_entry,
)
from .p10_safety_analysis_job_store_v2 import P10SafetyAnalysisJobStoreV2
from .resolved_project import canonical_sha256
from .reviewed_seam_anchor_set_commands import (
    verify_reviewed_seam_anchor_set_command,
)
from .seam_anchor_review_address import ExactSeamAnchorReviewAddress
from .seam_anchor_review_application import SeamAnchorReviewApplication
from .seam_review_publication import (
    FORMAT_VERSION, INTENT_VALUE, REQUEST_FORMAT,
)
from .seam_review_publication_records import (
    load_seam_review_publication_record,
)


class P10DynamicSeamAutoInputsV2Error(RuntimeError):
    """Raised when either current upstream cannot be selected uniquely."""

    def __init__(self, message, *, failure_code="source_changed",
                 terminal=True):
        super().__init__(message)
        self.failure_code, self.terminal = failure_code, terminal


@dataclass(frozen=True, slots=True)
class P10DynamicSeamAutoInputsV2:
    job_id: str
    safety_run_id: str
    package_id: str
    project_id: str
    continuous_proof_sha256: str
    reviewed_set_sha256: str
    reviewed_set_bundle_sha256: str
    candidate_sha256: str
    review_revision: int
    decision_sha256: str
    analyzer_sha256: str

    @property
    def identity(self):
        return {
            key: getattr(self, key) for key in (
                "job_id", "safety_run_id", "package_id", "project_id",
                "continuous_proof_sha256", "reviewed_set_sha256",
                "reviewed_set_bundle_sha256", "candidate_sha256",
                "review_revision", "decision_sha256", "analyzer_sha256",
            )
        }


def resolve_p10_dynamic_seam_auto_inputs_v2(
    state_root, job_id: str, safety_run_id: str,
) -> P10DynamicSeamAutoInputsV2:
    """Resolve one completed safety run and the package's current P10.5c."""

    try:
        safety = P10SafetyAnalysisJobStoreV2(state_root).load(safety_run_id)
        request = safety.request.document
        if safety.status != "completed" or request["job_id"] != job_id:
            raise P10DynamicSeamAutoInputsV2Error(
                "P10.4b v2 run is not the requested completed run"
            )
        _, continuous = P10SafetyAnalysisJobStoreV2(
            state_root
        ).read_result(safety_run_id)
        sealed = safety.events[-1].document["result"]
        continuous_sha = sealed["continuous_sha256"]
        if continuous.get("format_version") != 2:
            raise P10DynamicSeamAutoInputsV2Error(
                "P10.4b v2 continuous proof is not version two"
            )
        package_id = request["package_id"]
        entry = build_motion_policy_seam_review_entry(state_root, package_id)
        if entry["status"] != MANUAL_REVIEW_REQUIRED \
                or entry["blocking_relationships"]:
            raise P10DynamicSeamAutoInputsV2Error(
                "Current P10.5b review is not publishable"
            )
        address = ExactSeamAnchorReviewAddress(**entry["address"])
        prepared = SeamAnchorReviewApplication(state_root).prepare(address)
        history = prepared.history
        if history.revision_count != history.current_revision \
                or history.current_revision < 1 \
                or history.head_decision_sha256 is None \
                or prepared.candidate_sha256 != entry["candidate_sha256"]:
            raise P10DynamicSeamAutoInputsV2Error(
                "Current P10.5c head is absent or ambiguous"
            )
        publication_request = {
            "format": REQUEST_FORMAT, "format_version": FORMAT_VERSION,
            "intent": INTENT_VALUE, "package_id": package_id,
            "candidate_sha256": prepared.candidate_sha256,
            "review_revision": history.current_revision,
            "decision_sha256": history.head_decision_sha256,
        }
        receipt = load_seam_review_publication_record(
            state_root, entry["project_id"], package_id,
            publication_request,
        )
        if receipt is None or receipt.get("status") != "passed" \
                or receipt.get("source", {}).get("project_id") \
                    != entry["project_id"]:
            raise P10DynamicSeamAutoInputsV2Error(
                "Current P10.5c publication is unavailable"
            )
        output = receipt["address"]
        verified = verify_reviewed_seam_anchor_set_command(
            state_root, entry["project_id"],
            reviewed_set_sha256=output["reviewed_set_sha256"],
            bundle_sha256=output["bundle_sha256"],
        )
        if verified.candidate_sha256 != prepared.candidate_sha256 \
                or verified.review_revision != history.current_revision \
                or verified.decision_sha256 != history.head_decision_sha256:
            raise P10DynamicSeamAutoInputsV2Error(
                "P10.5c publication is historical rather than current"
            )
        return P10DynamicSeamAutoInputsV2(
            job_id, safety_run_id, package_id, entry["project_id"],
            continuous_sha, output["reviewed_set_sha256"],
            output["bundle_sha256"], prepared.candidate_sha256,
            history.current_revision, history.head_decision_sha256,
            p10_dynamic_seam_analyzer_sha256_v2(),
        )
    except P10DynamicSeamAutoInputsV2Error:
        raise
    except OSError as exc:
        raise P10DynamicSeamAutoInputsV2Error(
            "Automatic P10.5d v2 inputs are temporarily unavailable",
            failure_code="source_unavailable", terminal=False,
        ) from exc
    except Exception as exc:
        raise P10DynamicSeamAutoInputsV2Error(
            "Automatic P10.5d v2 inputs failed closed",
            failure_code="invalid_upstream", terminal=True,
        ) from exc


def p10_dynamic_seam_analyzer_sha256_v2() -> str:
    return canonical_sha256({
        "domain": "autospine-p10-dynamic-seam-analyzer/v2",
        "source_format": SOURCE_FORMAT,
        "source_format_version": SOURCE_VERSION,
        "bundle_inventory": list(DOCUMENT_NAMES),
        "release_authority": False,
    })


__all__ = [
    "P10DynamicSeamAutoInputsV2", "P10DynamicSeamAutoInputsV2Error",
    "p10_dynamic_seam_analyzer_sha256_v2",
    "resolve_p10_dynamic_seam_auto_inputs_v2",
]
