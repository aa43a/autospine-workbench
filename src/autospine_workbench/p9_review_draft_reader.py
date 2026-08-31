"""Strict, path-free discovery of pending P9 depth-policy drafts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any

from .current_project_chain import CurrentProjectChain, chain_is_current
from .http_json_request import decode_json_object
from .p9_review_draft_validation import (
    approved_policy_from_proposal,
    require_p9_review_draft_contract,
)
from .resolved_project import canonical_sha256
from . import motion_policy_review_package_files as files


LIST_FORMAT = "autospine-motion-policy-draft-list"
DETAIL_FORMAT = "autospine-motion-policy-review-draft-detail"
FORMAT_VERSION = 1
_SHA = re.compile(r"^[0-9a-f]{64}$")


class P9ReviewDraftReadError(ValueError):
    """Raised when immutable draft evidence is absent or inconsistent."""


@dataclass(frozen=True, slots=True)
class P9ReviewDraftEvidence:
    directory: Path
    draft_id: str
    project_id: str
    motion_namespace: str
    clip_id: str
    manifest_sha256: str
    proposal_sha256: str
    foot_candidates_sha256: str
    evidence_sha256: str
    promotion_motion_id: str
    manifest: dict[str, Any]
    proposal: dict[str, Any]
    foot_candidates: dict[str, Any]


def list_p9_review_drafts(
    state_root: Path,
    *,
    current_project_chains: Mapping[str, CurrentProjectChain],
    project_ids: frozenset[str] | None = None,
) -> dict[str, Any]:
    """List every valid draft, recommending only one current-chain draft."""

    rows, skipped = [], 0
    for directory in _directories(state_root):
        if project_ids is not None and directory.name not in project_ids:
            continue
        if not (directory / "draft-manifest.json").exists():
            continue
        try:
            draft = _load(directory)
            rows.append(_summary(draft, current_project_chains))
        except (P9ReviewDraftReadError, ValueError):
            skipped += 1
    rows.sort(key=lambda row: (row["project_id"], row["motion_namespace"]))
    current = [row for row in rows if row["authoring_alignment"] == "current"]
    recommended = current[0]["draft_id"] if len(current) == 1 else None
    return {
        "format": LIST_FORMAT,
        "format_version": FORMAT_VERSION,
        "count": len(rows),
        "skipped_count": skipped,
        "recommended_draft_id": recommended,
        "drafts": rows,
    }


def get_p9_review_draft(
    state_root: Path,
    draft_id: str,
    *,
    current_project_chains: Mapping[str, CurrentProjectChain],
    project_ids: frozenset[str] | None = None,
) -> dict[str, Any]:
    """Return one exact draft as a path-free human-review projection."""

    draft = load_p9_review_draft_evidence(
        state_root, draft_id, project_ids=project_ids,
    )
    result = _summary(draft, current_project_chains)
    result.update({
        "format": DETAIL_FORMAT,
        "semantic_summary": {
            "pair_count": len(draft.proposal["pairs"]),
            "pairs": [{
                "pair_id": pair["pair_id"],
                "setup_front_slot": pair["setup_front_slot"],
                "slots": [dict(slot) for slot in pair["slots"]],
            } for pair in draft.proposal["pairs"]],
        },
    })
    return result


def load_p9_review_draft_evidence(
    state_root: Path, draft_id: str, *,
    project_ids: frozenset[str] | None = None,
) -> P9ReviewDraftEvidence:
    """Load one evidence-sealed draft by its content-derived identity."""

    if not isinstance(draft_id, str) or not _SHA.fullmatch(draft_id):
        raise P9ReviewDraftReadError("P9 review draft id is invalid")
    for directory in _directories(state_root):
        if project_ids is not None and directory.name not in project_ids:
            continue
        if not (directory / "draft-manifest.json").exists():
            continue
        try:
            draft = _load(directory)
        except (P9ReviewDraftReadError, ValueError):
            continue
        if draft.draft_id == draft_id:
            return draft
    raise P9ReviewDraftReadError("No exact P9 review draft has this identity")


def _load(directory: Path) -> P9ReviewDraftEvidence:
    try:
        _require_inventory(directory)
        project = directory.name
        namespace = directory.parent.name
        manifest = _document(directory / "draft-manifest.json", 1024 * 1024)
        proposal = _document(
            directory / "depth-pair-policy.proposal.json", 1024 * 1024,
        )
        foot = _document(
            directory / "foot-lock-candidates.json", files.MAX_CANDIDATE_BYTES,
        )
        shared = directory.parent / "shared"
        evidence = _document(
            shared / "kimodo-policy-evidence.json", files.MAX_CANDIDATE_BYTES,
        )
        require_p9_review_draft_contract(
            manifest, proposal, foot, project, namespace,
        )
        identities = {
            "manifest": canonical_sha256(manifest),
            "proposal": canonical_sha256(proposal),
            "foot": canonical_sha256(foot),
            "evidence": canonical_sha256(evidence),
        }
        outputs = manifest["outputs"]
        if outputs != {
            "kimodo_policy_evidence_sha256": identities["evidence"],
            "foot_candidates_sha256": identities["foot"],
            "depth_pair_policy_proposal_sha256": identities["proposal"],
        }:
            raise P9ReviewDraftReadError("P9 draft output identities differ")
        draft_id = canonical_sha256({
            "domain": "autospine-motion-policy-review-draft-id/v1",
            "project_id": project,
            "motion_namespace": namespace,
            "manifest_sha256": identities["manifest"],
            "proposal_sha256": identities["proposal"],
            "foot_candidates_sha256": identities["foot"],
            "evidence_sha256": identities["evidence"],
        })
        return P9ReviewDraftEvidence(
            directory=directory,
            draft_id=draft_id,
            project_id=project,
            motion_namespace=namespace,
            clip_id=manifest["clip_id"],
            manifest_sha256=identities["manifest"],
            proposal_sha256=identities["proposal"],
            foot_candidates_sha256=identities["foot"],
            evidence_sha256=identities["evidence"],
            promotion_motion_id=_promotion_motion_id(namespace, draft_id),
            manifest=manifest,
            proposal=proposal,
            foot_candidates=foot,
        )
    except P9ReviewDraftReadError:
        raise
    except (KeyError, OSError, TypeError, ValueError) as exc:
        raise P9ReviewDraftReadError("P9 review draft is invalid") from exc


def _summary(draft, current) -> dict[str, Any]:
    p3 = draft.proposal["source"]["p3"]
    return {
        "format": DETAIL_FORMAT,
        "format_version": FORMAT_VERSION,
        "draft_id": draft.draft_id,
        "project_id": draft.project_id,
        "motion_namespace": draft.motion_namespace,
        "clip_id": draft.clip_id,
        "manifest_sha256": draft.manifest_sha256,
        "proposal_sha256": draft.proposal_sha256,
        "foot_candidates_sha256": draft.foot_candidates_sha256,
        "promotion_motion_id": draft.promotion_motion_id,
        "pair_count": len(draft.proposal["pairs"]),
        "authoring_alignment": "current" if chain_is_current(
            draft.project_id,
            p3["resolved_project_sha256"],
            p3["layer_manifest_sha256"],
            current,
        ) else "historical",
    }


def _require_inventory(directory: Path) -> None:
    motion = directory.parent
    entries = _entries(motion)
    if set(entries) != {"shared", directory.name}:
        raise P9ReviewDraftReadError("P9 draft directory inventory differs")
    if set(_entries(entries["shared"])) != {"kimodo-policy-evidence.json"}:
        raise P9ReviewDraftReadError("P9 draft shared inventory differs")
    if set(_entries(directory)) != {
        "depth-pair-policy.proposal.json", "foot-lock-candidates.json",
        "draft-manifest.json",
    }:
        raise P9ReviewDraftReadError("P9 draft project inventory differs")


def _entries(directory: Path) -> dict[str, Path]:
    files.require_directory(directory)
    children = list(directory.iterdir())
    if len(children) > 8 or len({child.name.casefold() for child in children}) != len(children):
        raise P9ReviewDraftReadError("P9 draft inventory is ambiguous")
    if any(files.is_linklike(child) for child in children):
        raise P9ReviewDraftReadError("P9 draft inventory contains an alias")
    return {child.name: child for child in children}


def _document(path: Path, maximum: int) -> dict[str, Any]:
    text = files.read_text(path, maximum, path.parent)
    value = decode_json_object(text.encode("utf-8"))
    canonical = json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    )
    if text != canonical:
        raise P9ReviewDraftReadError("P9 draft evidence is not canonical")
    return value


def _promotion_motion_id(namespace: str, draft_id: str) -> str:
    base = namespace[:-6] if namespace.endswith("-draft") else namespace
    base = base[:108].rstrip("._-") or "motion-policy"
    return f"{base}-p{draft_id[:12]}"


def _directories(state_root: Path) -> list[Path]:
    try:
        return files.package_directories(state_root)
    except files.MotionPolicyReviewPackageFilesError as exc:
        raise P9ReviewDraftReadError(
            "P9 review draft inventory is unavailable"
        ) from exc


__all__ = [
    "P9ReviewDraftEvidence", "P9ReviewDraftReadError",
    "approved_policy_from_proposal", "get_p9_review_draft",
    "list_p9_review_drafts", "load_p9_review_draft_evidence",
]
