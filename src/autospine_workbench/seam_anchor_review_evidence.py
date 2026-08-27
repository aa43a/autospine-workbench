"""Exact, path-free source-image evidence for P10.5b seam review."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from pathlib import Path
from typing import Any

from .manifest_artifacts import LayerManifestError, require_sha256
from .mesh_source_images import (
    VerifiedMeshSourceReader,
    VerifiedMeshSourceReaderError,
)
from .seam_anchor_review_address import ExactSeamAnchorReviewAddress
from .seam_anchor_review_application_models import PreparedSeamAnchorReview
from .seam_anchor_review_replay_cache import SeamAnchorReviewReplayCache


class SeamAnchorReviewEvidenceError(RuntimeError):
    """Raised when exact attachment evidence cannot be verified safely."""


class SeamAnchorReviewEvidenceNotFound(SeamAnchorReviewEvidenceError):
    """Raised when a subordinate candidate evidence address is not exact."""


@dataclass(frozen=True, slots=True)
class SeamAnchorReviewAttachmentRef:
    option_id: str
    attachment_role: str
    attachment_id: str
    attachment_type: str
    image_sha256: str
    width: int
    height: int


@dataclass(frozen=True, slots=True)
class SeamAnchorReviewAttachmentImage:
    image_sha256: str
    width: int
    height: int
    _png_bytes: bytes = field(repr=False)

    @property
    def png_bytes(self) -> bytes:
        return self._png_bytes


class SeamAnchorReviewEvidenceRepository:
    """Project candidate-referenced P3 source images without storage paths."""

    def __init__(
        self, state_root: Path, *,
        replay_cache: SeamAnchorReviewReplayCache | None = None,
    ) -> None:
        self.state_root = Path(state_root)
        if replay_cache is not None and (
            type(replay_cache) is not SeamAnchorReviewReplayCache
            or not replay_cache.owns_state_root(self.state_root)
        ):
            raise SeamAnchorReviewEvidenceError(
                "Seam-review replay cache state root differs"
            )
        self.replay_cache = replay_cache

    def attachment_refs(
        self,
        address: ExactSeamAnchorReviewAddress,
        prepared: PreparedSeamAnchorReview,
    ) -> tuple[SeamAnchorReviewAttachmentRef, ...]:
        """Return two exact image references per candidate option."""

        try:
            source, refs = self._load(address, prepared)
            if len(source.images) < len({row.attachment_id for row in refs}):
                raise SeamAnchorReviewEvidenceError(
                    "Candidate attachment evidence is incomplete"
                )
            return refs
        except SeamAnchorReviewEvidenceError:
            raise
        except _FAILURES as exc:
            raise SeamAnchorReviewEvidenceError(
                "Candidate attachment evidence projection failed"
            ) from exc

    def image(
        self,
        address: ExactSeamAnchorReviewAddress,
        prepared: PreparedSeamAnchorReview,
        *,
        candidate_sha256: str,
        option_id: str,
        attachment_id: str,
        image_sha256: str,
    ) -> SeamAnchorReviewAttachmentImage:
        """Read one option-bound original PNG using its exact digest."""

        try:
            candidate_address = require_sha256(
                candidate_sha256, "Seam-review candidate digest"
            )
            image_address = require_sha256(
                image_sha256, "Seam-review attachment image digest"
            )
            if prepared.candidate_sha256 != candidate_address:
                raise SeamAnchorReviewEvidenceNotFound(
                    "Seam candidate evidence address is stale"
                )
            source, refs = self._load(address, prepared)
            matches = [
                row for row in refs
                if row.option_id == option_id
                and row.attachment_id == attachment_id
                and row.image_sha256 == image_address
            ]
            if len(matches) != 1:
                raise SeamAnchorReviewEvidenceNotFound(
                    "Attachment is not bound to the addressed seam option"
                )
            image = source.image_by_attachment.get(attachment_id)
            if image is None or image.image_sha256 != image_address:
                raise SeamAnchorReviewEvidenceNotFound(
                    "Attachment image address is stale"
                )
            raw = image.png_bytes
            if hashlib.sha256(raw).hexdigest() != image_address:
                raise SeamAnchorReviewEvidenceError(
                    "Attachment image bytes differ from their identity"
                )
            return SeamAnchorReviewAttachmentImage(
                image_address, image.width, image.height, bytes(raw)
            )
        except SeamAnchorReviewEvidenceError:
            raise
        except _FAILURES as exc:
            raise SeamAnchorReviewEvidenceError(
                "Candidate attachment image load failed"
            ) from exc

    def _load(self, address, prepared):
        if type(address) is not ExactSeamAnchorReviewAddress \
                or type(prepared) is not PreparedSeamAnchorReview \
                or prepared.address != address:
            raise SeamAnchorReviewEvidenceError(
                "Attachment evidence requires one exact prepared address"
            )
        source = self.replay_cache.load_source(address) \
            if self.replay_cache is not None \
            else VerifiedMeshSourceReader(self.state_root).load(
                *address.mesh_reader_arguments
            )
        refs = _candidate_attachment_refs(
            prepared.candidate_document, source
        )
        return source, refs


def _candidate_attachment_refs(candidate: dict[str, Any], source):
    images = source.image_by_attachment
    attachments = _attachment_types(source.rig)
    refs: list[SeamAnchorReviewAttachmentRef] = []
    option_ids: set[str] = set()
    for relationship in candidate.get("relationships", []):
        for option in relationship.get("options", []):
            option_id = option.get("option_id")
            if type(option_id) is not str or option_id in option_ids:
                raise SeamAnchorReviewEvidenceError(
                    "Candidate option inventory is invalid"
                )
            option_ids.add(option_id)
            for role in ("parent", "child"):
                identifier = option.get(f"{role}_attachment_id")
                kind = option.get(f"{role}_attachment_type")
                image = images.get(identifier)
                if image is None or attachments.get(identifier) != kind:
                    raise SeamAnchorReviewEvidenceError(
                        "Candidate attachment differs from exact P3 source"
                    )
                refs.append(SeamAnchorReviewAttachmentRef(
                    option_id, role, identifier, kind,
                    image.image_sha256, image.width, image.height,
                ))
    keys = [(row.option_id, row.attachment_id) for row in refs]
    if len(keys) != len(set(keys)):
        raise SeamAnchorReviewEvidenceError(
            "Candidate option attachment evidence is duplicated"
        )
    role_order = {"parent": 0, "child": 1}
    return tuple(sorted(
        refs, key=lambda row: (row.option_id, role_order[row.attachment_role])
    ))


def _attachment_types(rig: dict[str, Any]) -> dict[str, str]:
    rows = rig.get("attachments")
    if type(rows) is not list:
        raise SeamAnchorReviewEvidenceError("P3 attachment inventory is invalid")
    result: dict[str, str] = {}
    for row in rows:
        if type(row) is not dict or type(row.get("id")) is not str \
                or row["id"] in result \
                or row.get("type") not in {"region", "mesh"}:
            raise SeamAnchorReviewEvidenceError(
                "P3 attachment inventory is invalid"
            )
        result[row["id"]] = row["type"]
    return result


_FAILURES = (
    AttributeError, KeyError, LayerManifestError, OSError, OverflowError,
    RecursionError, RuntimeError, TypeError, UnicodeError, ValueError,
    VerifiedMeshSourceReaderError,
)
