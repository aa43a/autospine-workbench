"""Explicit human promotion of one pending Depth policy draft."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Mapping

from .current_project_chain import CurrentProjectChain, chain_is_current
from .depth_order_candidates import compile_depth_order_candidates
from .depth_pair_policy import depth_pair_policy_sha256
from .foot_lock_candidate_validation import require_foot_lock_candidates
from .mesh_bundle_reader import VerifiedMeshBundleReader
from .motion_retarget_bundle_reader import VerifiedMotionRetargetBundleReader
from .p9_policy_promotion_store import publish_promoted_review_package
from .p9_review_draft_reader import (
    approved_policy_from_proposal,
    load_p9_review_draft_evidence,
)
from .projected_motion_bundle_reader import VerifiedProjectedMotionBundleReader
from .motion_policy_review_packages import (
    get_motion_policy_review_package,
    list_motion_policy_review_packages,
)


INTENT = "depth-policy-draft-adoption-v1"
REQUEST_FORMAT = "autospine-depth-policy-draft-adoption-request"
RECEIPT_FORMAT = "autospine-depth-policy-draft-adoption-receipt"


class P9DraftPolicyAdoptionError(ValueError):
    """Raised when a request does not authorize one exact draft."""


class P9DraftPolicyAdoptionHistoricalError(P9DraftPolicyAdoptionError):
    """Raised when the draft no longer matches current authoring."""


class P9DraftPolicyAdoptionUnavailableError(RuntimeError):
    """Raised when exact compilation or immutable publication fails."""


@dataclass(frozen=True, slots=True)
class PreparedP9DraftPolicyAdoption:
    draft_id: str
    project_id: str
    motion_id: str
    clip_id: str
    manifest_sha256: str
    proposal_sha256: str
    foot_candidates_sha256: str
    policy_sha256: str
    depth_candidates_sha256: str
    documents: tuple[tuple[str, bytes], ...]


def prepare_p9_draft_policy_adoption(
    state_root: Path,
    draft_id: str,
    request: Mapping[str, Any],
    *,
    current_project_chains: Mapping[str, CurrentProjectChain],
) -> PreparedP9DraftPolicyAdoption:
    """Validate authority and compile exact outputs without writing state."""

    try:
        draft = load_p9_review_draft_evidence(state_root, draft_id)
        _require_request(request, draft)
        p3_source = draft.proposal["source"]["p3"]
        if not chain_is_current(
            draft.project_id,
            p3_source["resolved_project_sha256"],
            p3_source["layer_manifest_sha256"],
            current_project_chains,
        ):
            raise P9DraftPolicyAdoptionHistoricalError(
                "Historical P9 review drafts are read-only"
            )
        source = draft.manifest["source"]
        p3 = VerifiedMeshBundleReader(state_root).load(
            draft.project_id,
            source["p3"]["rig_sha256"],
            source["p3"]["bundle_sha256"],
        )
        p5 = VerifiedMotionRetargetBundleReader(state_root).load(
            draft.project_id,
            source["p5"]["instance_sha256"],
            source["p5"]["bundle_sha256"],
        )
        p8 = VerifiedProjectedMotionBundleReader(state_root).load(
            source["p8"]["motion_sha256"],
            source["p8"]["bundle_sha256"],
        )
        _require_exact_upstream_sources(source, p3, p5, p8)
        require_foot_lock_candidates(
            draft.foot_candidates,
            projected_bundle=p8,
            retarget_bundle=p5,
        )
        policy = approved_policy_from_proposal(draft.proposal)
        depth = compile_depth_order_candidates(p8, p5, p3, policy)
        documents = {
            "depth-pair-policy.json": _canonical(policy),
            "foot-lock-candidates.json": _canonical(draft.foot_candidates),
            "depth-order-candidates.json": depth.canonical_bytes,
        }
        return PreparedP9DraftPolicyAdoption(
            draft_id=draft.draft_id,
            project_id=draft.project_id,
            motion_id=draft.promotion_motion_id,
            clip_id=draft.clip_id,
            manifest_sha256=draft.manifest_sha256,
            proposal_sha256=draft.proposal_sha256,
            foot_candidates_sha256=draft.foot_candidates_sha256,
            policy_sha256=depth_pair_policy_sha256(policy),
            depth_candidates_sha256=depth.sha256,
            documents=tuple(sorted(documents.items())),
        )
    except P9DraftPolicyAdoptionError:
        raise
    except (KeyError, OSError, RuntimeError, TypeError, ValueError) as exc:
        raise P9DraftPolicyAdoptionUnavailableError(
            "The exact P9 depth-policy draft could not be compiled"
        ) from exc


def publish_p9_draft_policy_adoption(
    state_root: Path,
    prepared: PreparedP9DraftPolicyAdoption,
    *,
    current_project_chains: Mapping[str, CurrentProjectChain],
) -> dict[str, Any]:
    """CAS the draft again, publish, and exact-read the resulting package."""

    try:
        current = load_p9_review_draft_evidence(
            state_root, prepared.draft_id,
        )
        if (
            current.manifest_sha256 != prepared.manifest_sha256
            or current.proposal_sha256 != prepared.proposal_sha256
            or current.foot_candidates_sha256
            != prepared.foot_candidates_sha256
        ):
            raise P9DraftPolicyAdoptionError(
                "P9 review draft changed before publication"
            )
        reused = publish_promoted_review_package(
            state_root,
            prepared.motion_id,
            prepared.project_id,
            dict(prepared.documents),
        )
        listing = list_motion_policy_review_packages(
            state_root,
            current_project_chains=current_project_chains,
        )
        matches = [row for row in listing["packages"] if (
            row["project_id"] == prepared.project_id
            and row["motion_id"] == prepared.motion_id
            and row["authoring_alignment"] == "current"
            and row["identities"]["policy_sha256"]
            == prepared.policy_sha256
            and row["identities"]["depth_candidates_sha256"]
            == prepared.depth_candidates_sha256
        )]
        if len(matches) != 1:
            raise P9DraftPolicyAdoptionUnavailableError(
                "Promoted P9 review package could not be identified exactly"
            )
        package = get_motion_policy_review_package(
            state_root,
            matches[0]["package_id"],
            current_project_chains=current_project_chains,
        )
        return {
            "format": RECEIPT_FORMAT,
            "format_version": 1,
            "status": "passed",
            "draft_id": prepared.draft_id,
            "project_id": prepared.project_id,
            "motion_id": prepared.motion_id,
            "clip_id": prepared.clip_id,
            "reused": reused,
            "policy_sha256": prepared.policy_sha256,
            "depth_candidates_sha256": prepared.depth_candidates_sha256,
            "package_id": package["package_id"],
        }
    except P9DraftPolicyAdoptionError:
        raise
    except P9DraftPolicyAdoptionUnavailableError:
        raise
    except (KeyError, OSError, RuntimeError, TypeError, ValueError) as exc:
        raise P9DraftPolicyAdoptionUnavailableError(
            "The promoted P9 review package could not be verified"
        ) from exc


def _require_request(request: Mapping[str, Any], draft) -> None:
    expected = {
        "format", "format_version", "intent", "draft_id",
        "manifest_sha256", "proposal_sha256", "explicit_confirmation",
    }
    if not isinstance(request, Mapping) or set(request) != expected \
            or request.get("format") != REQUEST_FORMAT \
            or request.get("format_version") != 1 \
            or request.get("intent") != INTENT \
            or request.get("draft_id") != draft.draft_id \
            or request.get("manifest_sha256") != draft.manifest_sha256 \
            or request.get("proposal_sha256") != draft.proposal_sha256 \
            or request.get("explicit_confirmation") is not True:
        raise P9DraftPolicyAdoptionError(
            "P9 depth-policy adoption request is invalid"
        )


def _canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        dict(value), ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")


def _require_exact_upstream_sources(source, p3, p5, p8) -> None:
    p5_source = p5.source_addresses
    checks = (
        (source["p3"]["rig_sha256"], p3.rig_sha256),
        (source["p3"]["bundle_sha256"], p3.bundle_sha256),
        (source["p3"]["rig_sha256"], p5_source["p3_rig_sha256"]),
        (source["p3"]["bundle_sha256"], p5_source["p3_bundle_sha256"]),
        (source["p4"]["profile_sha256"], p5_source["p4_profile_sha256"]),
        (source["p4"]["bundle_sha256"], p5_source["p4_bundle_sha256"]),
        (source["p7"]["motion_sha256"], p5_source["motion_clip_sha256"]),
        (source["p7"]["bundle_sha256"], p5_source["motion_bundle_sha256"]),
        (source["p7"]["motion_sha256"], p8.p7_motion_sha256),
        (source["p7"]["bundle_sha256"], p8.p7_bundle_sha256),
        (source["p8"]["motion_sha256"], p8.projected_motion_sha256),
        (source["p8"]["bundle_sha256"], p8.bundle_sha256),
    )
    if p3.project_id != p5.project_id or p5.clip_id != p8.clip_id \
            or any(left != right for left, right in checks):
        raise P9DraftPolicyAdoptionError(
            "P9 draft upstream stage identities are cross-wired"
        )


__all__ = [
    "INTENT", "P9DraftPolicyAdoptionError",
    "P9DraftPolicyAdoptionHistoricalError",
    "P9DraftPolicyAdoptionUnavailableError",
    "PreparedP9DraftPolicyAdoption", "prepare_p9_draft_policy_adoption",
    "publish_p9_draft_policy_adoption",
]
