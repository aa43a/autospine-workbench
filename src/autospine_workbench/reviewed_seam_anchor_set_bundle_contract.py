"""Pure three-document contract for reviewed seam-anchor set bundles."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import json
from typing import Any

from .immutable_bundle_fs import ImmutableBundleFSError, framed_bundle_sha256
from .reviewed_seam_anchor_set_compiler import (
    ReviewedSeamAnchorSetCompilerError,
    compile_reviewed_seam_anchor_set,
)
from .reviewed_seam_anchor_set_profile import (
    MAX_DOCUMENT_BYTES as MAX_SET_BYTES,
)
from .reviewed_seam_anchor_set_validation import (
    ReviewedSeamAnchorSetValidationError,
    reviewed_seam_anchor_set_sha256,
)
from .seam_anchor_candidate_profile import (
    MAX_DOCUMENT_BYTES as MAX_CANDIDATE_BYTES,
)
from .seam_anchor_candidate_validation import (
    SeamAnchorCandidateValidationError,
    seam_anchor_candidates_sha256,
)
from .seam_anchor_review_decision_validation import (
    SeamAnchorReviewDecisionValidationError,
    seam_anchor_review_decision_sha256,
)
from .seam_anchor_review_json import canonical_json_bytes
from .seam_anchor_review_profile import (
    MAX_SEAM_ANCHOR_REVIEW_DOCUMENT_BYTES as MAX_DECISION_BYTES,
)


BUNDLE_ADDRESS_DOMAIN = (
    "autospine-reviewed-seam-anchor-set-bundle-address/v1"
)
DOCUMENT_NAMES = (
    "seam-anchor-candidates.json",
    "seam-anchor-review-decision.json",
    "reviewed-seam-anchor-set.json",
)
DOCUMENT_LIMITS = (
    MAX_CANDIDATE_BYTES,
    MAX_DECISION_BYTES,
    MAX_SET_BYTES,
)
MAX_TOTAL_BYTES = sum(DOCUMENT_LIMITS)


class ReviewedSeamAnchorSetBundleContractError(ValueError):
    """Raised when three proposed documents cannot be reproduced exactly."""


@dataclass(frozen=True, slots=True)
class ReviewedSeamAnchorSetBundleContract:
    """Frozen canonical inventory and its two exact content addresses."""

    project_id: str
    candidate_sha256: str
    decision_sha256: str
    review_revision: int
    set_sha256: str
    bundle_sha256: str
    _documents: tuple[tuple[str, bytes], ...] = field(repr=False)

    @property
    def document_bytes(self) -> dict[str, bytes]:
        return dict(self._documents)

    @property
    def inventory(self) -> tuple[str, ...]:
        return tuple(name for name, _data in self._documents)

    @property
    def identities(self) -> dict[str, str | int]:
        return {
            "candidate_sha256": self.candidate_sha256,
            "decision_sha256": self.decision_sha256,
            "review_revision": self.review_revision,
            "set_sha256": self.set_sha256,
            "bundle_sha256": self.bundle_sha256,
        }

    def document(self, name: str) -> dict[str, Any]:
        try:
            return json.loads(dict(self._documents)[name])
        except KeyError as exc:
            raise KeyError(name) from exc


def build_reviewed_seam_anchor_set_bundle_contract(
    candidates: Mapping[str, Any],
    decision: Mapping[str, Any],
    rig: Mapping[str, Any],
    reviewed_set: Mapping[str, Any],
) -> ReviewedSeamAnchorSetBundleContract:
    """Validate, recompile, canonicalize, and address all three documents."""

    try:
        candidate_sha = seam_anchor_candidates_sha256(candidates)
        decision_sha = seam_anchor_review_decision_sha256(decision)
        rebuilt = compile_reviewed_seam_anchor_set(
            candidates, decision, rig
        )
        set_sha = reviewed_seam_anchor_set_sha256(reviewed_set)
        provided_set = _document(reviewed_set, DOCUMENT_NAMES[2], 2)
        if rebuilt.sha256 != set_sha or rebuilt.canonical_bytes != provided_set:
            raise ReviewedSeamAnchorSetBundleContractError(
                "Reviewed seam-anchor set differs from exact recompilation"
            )
        values = (candidates, decision, rebuilt.document)
        items = tuple(
            (name, _document(value, name, index))
            for index, (name, value) in enumerate(
                zip(DOCUMENT_NAMES, values, strict=True)
            )
        )
        if sum(len(data) for _name, data in items) > MAX_TOTAL_BYTES:
            raise ReviewedSeamAnchorSetBundleContractError(
                "Reviewed seam-anchor bundle exceeds its total byte limit"
            )
        files = dict(items)
        return ReviewedSeamAnchorSetBundleContract(
            project_id=str(candidates["project_id"]),
            candidate_sha256=candidate_sha,
            decision_sha256=decision_sha,
            review_revision=int(decision["review"]["revision"]),
            set_sha256=set_sha,
            bundle_sha256=framed_bundle_sha256(
                BUNDLE_ADDRESS_DOMAIN, DOCUMENT_NAMES, files
            ),
            _documents=items,
        )
    except ReviewedSeamAnchorSetBundleContractError:
        raise
    except (
        ImmutableBundleFSError,
        KeyError,
        OverflowError,
        RecursionError,
        ReviewedSeamAnchorSetCompilerError,
        ReviewedSeamAnchorSetValidationError,
        SeamAnchorCandidateValidationError,
        SeamAnchorReviewDecisionValidationError,
        TypeError,
        UnicodeError,
        ValueError,
    ) as exc:
        raise ReviewedSeamAnchorSetBundleContractError(
            f"Reviewed seam-anchor bundle contract failed: {exc}"
        ) from exc


def _document(
    value: Mapping[str, Any], label: str, index: int,
) -> bytes:
    if type(value) is not dict:
        raise ReviewedSeamAnchorSetBundleContractError(
            f"{label} must be an exact JSON object"
        )
    data = canonical_json_bytes(value)
    if len(data) > DOCUMENT_LIMITS[index]:
        raise ReviewedSeamAnchorSetBundleContractError(
            f"{label} exceeds its byte limit"
        )
    return data


def reviewed_seam_anchor_set_bundle_address_sha256(
    files: Mapping[str, bytes],
) -> str:
    """Return the domain-separated address for one exact fixed inventory."""

    return framed_bundle_sha256(
        BUNDLE_ADDRESS_DOMAIN, DOCUMENT_NAMES, files
    )
