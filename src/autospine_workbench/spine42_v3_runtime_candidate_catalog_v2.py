"""Read-only discovery and conservative selection of P10.7b candidates."""

from __future__ import annotations

from dataclasses import dataclass
import re

from .p10_spine42_v3_completion_inventory_v2 import (
    P10Spine42V3CompletionInventoryV2Error,
    read_p10_spine42_v3_completion_inventory_v2,
)
from .spine42_v3_runtime_candidate_contract_v2 import (
    Spine42V3RuntimeCandidateContractV2Error,
    Spine42V3RuntimeCandidateV2,
)

CATALOG_FORMAT = "autospine-p10-spine42-v3-runtime-candidate-catalog-v2"
_SHA = re.compile(r"^[0-9a-f]{64}$")


class Spine42V3RuntimeCandidateCatalogV2Error(RuntimeError):
    """Raised when the candidate inventory cannot be evaluated safely."""


@dataclass(frozen=True, slots=True)
class Spine42V3RuntimeCandidateCatalogV2:
    candidates: tuple[Spine42V3RuntimeCandidateV2, ...]
    ambiguities: tuple[dict, ...]
    skips: tuple[dict, ...]
    enumerated_run_count: int
    selection: dict

    def public_document(self):
        return {
            "format": CATALOG_FORMAT, "format_version": 2,
            "candidates": [row.public_document()
                           for row in self.candidates],
            "ambiguities": [_copy(row) for row in self.ambiguities],
            "skips": [_copy(row) for row in self.skips],
            "counts": {
                "enumerated_runs": self.enumerated_run_count,
                "eligible_candidates": len(self.candidates),
                "ambiguous_families": len(self.ambiguities),
                "skips": len(self.skips),
            },
            "selection": _copy(self.selection),
            "runner_execution_authorized": False,
            "publication_authorized": False,
        }

def read_spine42_v3_runtime_candidate_catalog_v2(
    state_root, *, continuation_spine_run_id=None,
):
    """Build a zero-write catalog; uniqueness never implies authorization."""

    try:
        inventory = read_p10_spine42_v3_completion_inventory_v2(state_root)
    except P10Spine42V3CompletionInventoryV2Error as exc:
        raise Spine42V3RuntimeCandidateCatalogV2Error(
            "Runtime candidate inventory is unavailable") from exc
    candidates, skips = [], [
        {"scope": "run", "family_id": None,
         **row.public_document()} for row in inventory.skipped
    ]
    for family in inventory.families:
        if family.issue_code is not None:
            continue
        head = family.head
        if head.status != "completed":
            skips.append({
                "scope": "family", "family_id": family.family_id,
                "spine_run_id": head.run_id,
                "code": "head_not_completed",
            })
            continue
        try:
            candidates.append(
                Spine42V3RuntimeCandidateV2.from_completed_head(head))
        except Spine42V3RuntimeCandidateContractV2Error:
            skips.append({
                "scope": "family", "family_id": family.family_id,
                "spine_run_id": head.run_id,
                "code": "invalid_completion",
            })
    # These sorts are presentation-only; chain attempts established every head.
    candidates.sort(key=lambda row: (
        row.document["completion"]["project_id"],
        row.document["completion"]["clip_id"], row.spine_run_id,
    ))
    ambiguities = tuple(sorted(
        inventory.ambiguities, key=lambda row: row["family_id"]))
    skips = tuple(sorted(
        skips, key=lambda row: (row["spine_run_id"], row["code"])))
    selection = _selection(
        tuple(candidates), ambiguities, skips, inventory,
        continuation_spine_run_id,
    )
    return Spine42V3RuntimeCandidateCatalogV2(
        tuple(candidates), ambiguities, skips,
        len(inventory.enumerated_run_ids), selection,
    )


def revalidate_spine42_v3_runtime_candidate_entry_v2(
    state_root, candidate_id, entry_sha256,
):
    """Rebuild the zero-write catalog before matching an exact entry."""

    catalog = read_spine42_v3_runtime_candidate_catalog_v2(state_root)
    return _require_exact_entry(catalog, candidate_id, entry_sha256)


def _require_exact_entry(catalog, candidate_id, entry_sha256):
    if not _is_sha(candidate_id) or not _is_sha(entry_sha256):
        raise Spine42V3RuntimeCandidateCatalogV2Error(
            "Runtime candidate entry address is invalid")
    matches = [row for row in catalog.candidates
               if row.candidate_id == candidate_id
               and row.entry_sha256 == entry_sha256]
    if len(matches) != 1:
        raise Spine42V3RuntimeCandidateCatalogV2Error(
            "Runtime candidate entry is stale or unavailable")
    return matches[0]


def _selection(candidates, ambiguities, skips, inventory, continuation):
    if continuation is not None:
        if not _is_sha(continuation):
            return _decision("blocked", "continuation_invalid", None)
        exact = [row for row in candidates
                 if row.spine_run_id == continuation]
        if len(exact) == 1:
            return _decision(
                "continuation", "exact_continuation", continuation, exact[0])
        if continuation not in inventory.enumerated_run_ids:
            reason = "continuation_not_found"
        else:
            family = inventory.family_containing(continuation)
            invalid = any(
                row["spine_run_id"] == continuation
                and row["code"] in {
                    "invalid_run", "invalid_completion",
                    "invalid_provenance",
                }
                for row in skips
            )
            reason = "continuation_invalid" if invalid else (
                "continuation_ambiguous" if family is not None
                and family.issue_code is not None
                else "continuation_ineligible"
            )
        return _decision("blocked", reason, continuation)
    unresolved = bool(ambiguities or skips)
    if len(candidates) == 1 and not unresolved:
        return _decision(
            "automatic", "unique_eligible_candidate", None, candidates[0])
    if len(candidates) > 1:
        return _decision("selection_required", "multiple_candidates", None)
    if len(candidates) == 1:
        return _decision("selection_required", "unresolved_inventory", None)
    if unresolved:
        return _decision("blocked", "unresolved_inventory", None)
    return _decision("none", "no_candidates", None)


def _decision(mode, reason, requested, candidate=None):
    return {
        "mode": mode, "reason_code": reason,
        "requested_spine_run_id": requested,
        "recommended_candidate_id": None if candidate is None
            else candidate.candidate_id,
        "recommended_entry_sha256": None if candidate is None
            else candidate.entry_sha256,
    }


def _is_sha(value):
    return type(value) is str and _SHA.fullmatch(value) is not None


def _copy(value):
    if isinstance(value, dict):
        return {key: _copy(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_copy(item) for item in value]
    return value


__all__ = [
    "CATALOG_FORMAT", "Spine42V3RuntimeCandidateCatalogV2",
    "Spine42V3RuntimeCandidateCatalogV2Error",
    "read_spine42_v3_runtime_candidate_catalog_v2",
    "revalidate_spine42_v3_runtime_candidate_entry_v2",
]
