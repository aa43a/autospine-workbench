"""Strict snapshot validation for reviewed seam-anchor set bundles."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any

from .immutable_bundle_fs import ImmutableBundleSnapshot
from .reviewed_seam_anchor_set_bundle_contract import (
    DOCUMENT_LIMITS,
    DOCUMENT_NAMES,
    MAX_TOTAL_BYTES,
    ReviewedSeamAnchorSetBundleContractError,
    build_reviewed_seam_anchor_set_bundle_contract,
    reviewed_seam_anchor_set_bundle_address_sha256,
)
from .reviewed_seam_anchor_set_bundle_fs import NAMESPACE
from .reviewed_seam_anchor_set_validation import (
    ReviewedSeamAnchorSetValidationError,
    require_reviewed_seam_anchor_set,
    reviewed_seam_anchor_set_sha256,
)
from .safe_input_files import SafeInputFileError, strict_json_object
from .seam_anchor_candidate_validation import (
    SeamAnchorCandidateValidationError,
    require_seam_anchor_candidates,
)
from .seam_anchor_review_decision_validation import (
    SeamAnchorReviewDecisionValidationError,
    require_seam_anchor_review_decision,
)
from .seam_anchor_review_json import canonical_json_bytes


class ReviewedSeamAnchorSetBundleIntegrityError(ValueError):
    """Raised when stored bundle bytes cannot be reproduced exactly."""


@dataclass(frozen=True, slots=True)
class VerifiedReviewedSeamAnchorSetBundle:
    """Frozen verified identities with copy-isolated JSON accessors."""

    path: Path
    project_id: str
    candidate_sha256: str
    decision_sha256: str
    review_revision: int
    set_sha256: str
    bundle_sha256: str
    _documents: tuple[tuple[str, bytes], ...] = field(repr=False)

    @property
    def inventory(self) -> tuple[str, ...]:
        return tuple(name for name, _data in self._documents)

    @property
    def document_bytes(self) -> dict[str, bytes]:
        return dict(self._documents)

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

    @property
    def candidates(self) -> dict[str, Any]:
        return self.document(DOCUMENT_NAMES[0])

    @property
    def decision(self) -> dict[str, Any]:
        return self.document(DOCUMENT_NAMES[1])

    @property
    def reviewed_set(self) -> dict[str, Any]:
        return self.document(DOCUMENT_NAMES[2])


def reviewed_seam_anchor_set_bundle_documents(
    snapshot: ImmutableBundleSnapshot,
) -> dict[str, dict[str, Any]]:
    """Parse one exact inventory and perform detached document validation."""

    try:
        raw = _raw_documents(snapshot)
        documents = {
            name: strict_json_object(raw[name], name)
            for name in DOCUMENT_NAMES
        }
        require_seam_anchor_candidates(documents[DOCUMENT_NAMES[0]])
        require_seam_anchor_review_decision(documents[DOCUMENT_NAMES[1]])
        require_reviewed_seam_anchor_set(documents[DOCUMENT_NAMES[2]])
        if any(
            canonical_json_bytes(documents[name]) != raw[name]
            for name in DOCUMENT_NAMES
        ):
            raise ReviewedSeamAnchorSetBundleIntegrityError(
                "Reviewed seam-anchor documents are not canonical JSON"
            )
        set_sha = reviewed_seam_anchor_set_sha256(documents[DOCUMENT_NAMES[2]])
        if set_sha != snapshot.primary_sha256 \
                or reviewed_seam_anchor_set_bundle_address_sha256(raw) \
                != snapshot.bundle_sha256:
            raise ReviewedSeamAnchorSetBundleIntegrityError(
                "Reviewed seam-anchor bytes differ from their exact address"
            )
        return documents
    except ReviewedSeamAnchorSetBundleIntegrityError:
        raise
    except _VALIDATION_ERRORS as exc:
        raise ReviewedSeamAnchorSetBundleIntegrityError(
            f"Reviewed seam-anchor snapshot parsing failed: {exc}"
        ) from exc


def verify_reviewed_seam_anchor_set_bundle_snapshot(
    snapshot: ImmutableBundleSnapshot,
    *,
    expected_project_id: str,
    expected_set_sha256: str,
    expected_bundle_sha256: str,
    candidates: Mapping[str, Any],
    decision: Mapping[str, Any],
    rig: Mapping[str, Any],
) -> VerifiedReviewedSeamAnchorSetBundle:
    """Recompile the set and compare every canonical byte and address."""

    try:
        documents = reviewed_seam_anchor_set_bundle_documents(snapshot)
        contract = build_reviewed_seam_anchor_set_bundle_contract(
            candidates, decision, rig, documents[DOCUMENT_NAMES[2]]
        )
        raw = dict(zip(snapshot.ordered_names, snapshot.payloads, strict=True))
        if contract.document_bytes != raw \
                or documents[DOCUMENT_NAMES[0]] != candidates \
                or documents[DOCUMENT_NAMES[1]] != decision:
            raise ReviewedSeamAnchorSetBundleIntegrityError(
                "Reviewed seam-anchor bundle differs from exact replay"
            )
        if contract.project_id != expected_project_id \
                or contract.set_sha256 != expected_set_sha256 \
                or contract.bundle_sha256 != expected_bundle_sha256:
            raise ReviewedSeamAnchorSetBundleIntegrityError(
                "Reviewed seam-anchor bundle differs from explicit address"
            )
        _require_address(snapshot.path, contract)
        return VerifiedReviewedSeamAnchorSetBundle(
            path=snapshot.path,
            project_id=contract.project_id,
            candidate_sha256=contract.candidate_sha256,
            decision_sha256=contract.decision_sha256,
            review_revision=contract.review_revision,
            set_sha256=contract.set_sha256,
            bundle_sha256=contract.bundle_sha256,
            _documents=tuple((name, raw[name]) for name in DOCUMENT_NAMES),
        )
    except ReviewedSeamAnchorSetBundleIntegrityError:
        raise
    except (
        AttributeError,
        KeyError,
        OSError,
        OverflowError,
        RecursionError,
        ReviewedSeamAnchorSetBundleContractError,
        TypeError,
        UnicodeError,
        ValueError,
    ) as exc:
        raise ReviewedSeamAnchorSetBundleIntegrityError(
            f"Reviewed seam-anchor bundle integrity failed: {exc}"
        ) from exc


def _raw_documents(snapshot: ImmutableBundleSnapshot) -> dict[str, bytes]:
    if type(snapshot) is not ImmutableBundleSnapshot \
            or snapshot.ordered_names != DOCUMENT_NAMES:
        raise ReviewedSeamAnchorSetBundleIntegrityError(
            "Reviewed seam-anchor snapshot inventory is invalid"
        )
    total = 0
    raw = {}
    for index, (name, data) in enumerate(
        zip(snapshot.ordered_names, snapshot.payloads, strict=True)
    ):
        if not isinstance(data, bytes) or len(data) > DOCUMENT_LIMITS[index]:
            raise ReviewedSeamAnchorSetBundleIntegrityError(
                f"{name} exceeds its snapshot byte limit"
            )
        total += len(data)
        raw[name] = data
    if total > MAX_TOTAL_BYTES:
        raise ReviewedSeamAnchorSetBundleIntegrityError(
            "Reviewed seam-anchor snapshot exceeds its total byte limit"
        )
    return raw


def _require_address(path: Path, contract) -> None:
    parts = (
        path.name,
        path.parent.name,
        path.parent.parent.name,
        path.parent.parent.parent.name,
        path.parent.parent.parent.parent.name,
    )
    expected = (
        contract.bundle_sha256,
        contract.set_sha256,
        NAMESPACE,
        contract.project_id,
        "builds",
    )
    if parts != expected:
        raise ReviewedSeamAnchorSetBundleIntegrityError(
            "Reviewed seam-anchor content-address path is invalid"
        )


_VALIDATION_ERRORS = (
    KeyError,
    OSError,
    OverflowError,
    RecursionError,
    ReviewedSeamAnchorSetValidationError,
    SafeInputFileError,
    SeamAnchorCandidateValidationError,
    SeamAnchorReviewDecisionValidationError,
    TypeError,
    UnicodeError,
    ValueError,
)
