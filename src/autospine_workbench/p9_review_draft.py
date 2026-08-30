"""Prepare a non-authoritative P9 review draft in a fresh namespace."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

from .depth_order_inputs import require_depth_order_inputs
from .depth_pair_policy_proposal import (
    compile_depth_pair_policy_proposal,
)
from .foot_lock_candidate import compile_foot_lock_candidates
from .ik_bundle_reader import VerifiedIkBundleReader
from .kimodo_policy_evidence import compile_kimodo_policy_evidence
from .manifest_artifacts import require_safe_token
from .mesh_bundle_reader import VerifiedMeshBundleReader
from .motion_bundle_reader import VerifiedMotionBundleReader
from .motion_retarget_bundle_reader import VerifiedMotionRetargetBundleReader
from .p9_review_draft_store import (
    P9ReviewDraftStoreError,
    publish_p9_review_draft,
    require_real_state_root,
)
from .projected_motion_bundle_reader import VerifiedProjectedMotionBundleReader
from .resolved_project import canonical_sha256


FORMAT = "autospine-motion-policy-review-draft"
FORMAT_VERSION = 1
_SHARED_FILE = "kimodo-policy-evidence.json"
class P9ReviewDraftError(RuntimeError):
    """Raised when a draft cannot be reproduced or safely published."""


@dataclass(frozen=True, slots=True)
class P9ReviewDraftResult:
    motion_namespace: str
    project_id: str
    reused: bool
    manifest_sha256: str
    foot_candidates_sha256: str
    proposal_sha256: str


def prepare_p9_review_draft(
    state_root: Path,
    project_id: str,
    motion_namespace: str,
    *,
    p3_rig_sha256: str,
    p3_bundle_sha256: str,
    p4_profile_sha256: str,
    p4_bundle_sha256: str,
    motion_instance_sha256: str,
    motion_retarget_bundle_sha256: str,
    p7_motion_sha256: str,
    p7_bundle_sha256: str,
    p8_motion_sha256: str,
    p8_bundle_sha256: str,
    first_slot_id: str,
    second_slot_id: str,
    pair_id: str,
    max_correction_reference_ratio: float = 0.25,
    max_residual_px: float = 8.0,
) -> P9ReviewDraftResult:
    """Verify one exact chain and publish evidence plus a pending proposal."""

    try:
        project = require_safe_token(project_id, "Project id")
        if project.casefold() == "shared":
            raise P9ReviewDraftError(
                "Project id is reserved by the review layout"
            )
        namespace = require_safe_token(
            motion_namespace, "Motion review namespace"
        )
        state = require_real_state_root(Path(state_root))
        p3 = VerifiedMeshBundleReader(state).load(
            project, p3_rig_sha256, p3_bundle_sha256
        )
        p4 = VerifiedIkBundleReader(state).load(
            project, p4_profile_sha256, p4_bundle_sha256,
            mesh_bundle=p3,
        )
        p5 = VerifiedMotionRetargetBundleReader(state).load(
            project, motion_instance_sha256,
            motion_retarget_bundle_sha256,
        )
        p7 = VerifiedMotionBundleReader(state).load(
            p7_motion_sha256, p7_bundle_sha256
        )
        p8 = VerifiedProjectedMotionBundleReader(state).load(
            p8_motion_sha256, p8_bundle_sha256
        )
        _require_one_chain(p3, p4, p5, p7, p8)
        evidence = compile_kimodo_policy_evidence(p7, p8)
        foot = compile_foot_lock_candidates(
            p8, p5,
            max_correction_reference_ratio=max_correction_reference_ratio,
            max_residual_px=max_residual_px,
        )
        proposal = compile_depth_pair_policy_proposal(
            require_depth_order_inputs(p8, p5, p3),
            motion_id=namespace,
            pair_id=pair_id,
            first_slot_id=first_slot_id,
            second_slot_id=second_slot_id,
        )
        files = _draft_files(
            project, namespace, p3, p4, p5, p7, p8,
            evidence.document, evidence.sha256,
            foot.document, foot.sha256, proposal,
        )
        reused = publish_p9_review_draft(
            state, namespace, project, files
        )
        manifest = json.loads(files[f"{project}/draft-manifest.json"])
        return P9ReviewDraftResult(
            motion_namespace=namespace,
            project_id=project,
            reused=reused,
            manifest_sha256=canonical_sha256(manifest),
            foot_candidates_sha256=foot.sha256,
            proposal_sha256=canonical_sha256(proposal),
        )
    except P9ReviewDraftError:
        raise
    except (
        AttributeError, KeyError, OSError, OverflowError, RuntimeError,
        TypeError, ValueError, P9ReviewDraftStoreError,
    ) as exc:
        raise P9ReviewDraftError(
            f"P9 review draft preparation failed: {exc}"
        ) from exc


def _require_one_chain(p3, p4, p5, p7, p8) -> None:
    source = p5.source_addresses
    expected = {
        "p3_rig_sha256": p3.rig_sha256,
        "p3_bundle_sha256": p3.bundle_sha256,
        "p4_profile_sha256": p4.profile_sha256,
        "p4_bundle_sha256": p4.bundle_sha256,
        "motion_clip_sha256": p7.clip_sha256,
        "motion_bundle_sha256": p7.bundle_sha256,
    }
    if source != expected or p4.p3_rig_sha256 != p3.rig_sha256 \
            or p4.p3_bundle_sha256 != p3.bundle_sha256:
        raise P9ReviewDraftError("P3/P4/P5 identities are cross-wired")
    if p8.p7_motion_sha256 != p7.clip_sha256 \
            or p8.p7_bundle_sha256 != p7.bundle_sha256:
        raise P9ReviewDraftError("P7/P8 identities are cross-wired")


def _draft_files(
    project, namespace, p3, p4, p5, p7, p8,
    evidence, evidence_sha, foot, foot_sha, proposal,
) -> dict[str, bytes]:
    evidence_bytes = _canonical(evidence)
    foot_bytes = _canonical(foot)
    proposal_bytes = _canonical(proposal)
    if _sha(evidence_bytes) != evidence_sha or _sha(foot_bytes) != foot_sha:
        raise P9ReviewDraftError(
            "P9 draft compiler identity differs from canonical content"
        )
    output_identities = {
        "kimodo_policy_evidence_sha256": evidence_sha,
        "foot_candidates_sha256": foot_sha,
        "depth_pair_policy_proposal_sha256": _sha(proposal_bytes),
    }
    manifest = {
        "format": FORMAT,
        "format_version": FORMAT_VERSION,
        "status": "pending_human_depth_policy_review",
        "authority": {
            "approved_depth_policy": False,
            "depth_candidates_emitted": False,
            "p9_adoption_emitted": False,
        },
        "project_id": project,
        "motion_namespace": namespace,
        "clip_id": p8.clip_id,
        "source": {
            "p3": {"rig_sha256": p3.rig_sha256,
                   "bundle_sha256": p3.bundle_sha256},
            "p4": {"profile_sha256": p4.profile_sha256,
                   "bundle_sha256": p4.bundle_sha256},
            "p5": {"instance_sha256": p5.instance_sha256,
                   "bundle_sha256": p5.bundle_sha256},
            "p7": {"motion_sha256": p7.clip_sha256,
                   "bundle_sha256": p7.bundle_sha256},
            "p8": {"motion_sha256": p8.projected_motion_sha256,
                   "bundle_sha256": p8.bundle_sha256},
        },
        "outputs": output_identities,
    }
    return {
        f"shared/{_SHARED_FILE}": evidence_bytes,
        f"{project}/depth-pair-policy.proposal.json": proposal_bytes,
        f"{project}/foot-lock-candidates.json": foot_bytes,
        f"{project}/draft-manifest.json": _canonical(manifest),
    }


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()
