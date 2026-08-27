"""Pure P10.5a compiler for static, review-only seam anchor options."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
from typing import Any

from .mesh_bundle_integrity import VerifiedMeshBundle
from .seam_anchor_candidate_geometry import (
    SeamAnchorCandidateGeometryError,
    derive_seam_candidate_relationships,
)
from .seam_anchor_candidate_profile import (
    CLAIMS,
    FORMAT,
    FORMAT_VERSION,
    RELEASE_GATE,
    SEMANTICS,
    candidate_generator_profile,
)
from .seam_anchor_candidate_validation import (
    SeamAnchorCandidateValidationError,
    require_seam_anchor_candidates,
    seam_anchor_candidates_sha256,
)
from .seam_anchor_inputs import (
    SeamAnchorInputError,
    require_seam_anchor_inputs,
)
from .seam_anchor_runtime_guard import require_candidate_runtime_consistency


class SeamAnchorCandidateError(ValueError):
    """Raised when exact static inputs cannot produce candidate evidence."""


@dataclass(frozen=True, slots=True)
class SeamAnchorCandidates:
    """Frozen canonical candidate value; accessors return isolated data."""

    _canonical_json: str

    @property
    def document(self) -> dict[str, Any]:
        return json.loads(self._canonical_json)

    @property
    def canonical_bytes(self) -> bytes:
        return self._canonical_json.encode("utf-8")

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes).hexdigest()


def compile_seam_anchor_candidates(
    layer_manifest: Mapping[str, Any],
    mesh_bundle: VerifiedMeshBundle,
) -> SeamAnchorCandidates:
    """Compile exact setup-alpha options; never choose or animate anchors."""

    try:
        require_candidate_runtime_consistency()
        inputs = require_seam_anchor_inputs(layer_manifest, mesh_bundle)
        relationships = derive_seam_candidate_relationships(inputs)
        options = [
            option for relationship in relationships
            for option in relationship["options"]
        ]
        document = {
            "format": FORMAT,
            "format_version": FORMAT_VERSION,
            "project_id": inputs.project_id,
            "source": inputs.source,
            "generator": candidate_generator_profile(),
            "semantics": _copy(SEMANTICS),
            "relationships": relationships,
            "claims": _copy(CLAIMS),
            "release_gate": _copy(RELEASE_GATE),
            "summary": {
                "status": "manual_review_required",
                "relationship_count": len(relationships),
                "review_required_count": sum(
                    row["status"] == "review_required"
                    for row in relationships
                ),
                "unobservable_count": sum(
                    row["status"] == "unobservable"
                    for row in relationships
                ),
                "option_count": len(options),
                "candidate_option_count": sum(
                    row["status"] == "candidate" for row in options
                ),
                "unavailable_option_count": sum(
                    row["status"] == "unavailable" for row in options
                ),
                "anchor_pair_count": sum(
                    len(row["anchors"]) for row in options
                ),
            },
        }
        require_seam_anchor_candidates(document)
        result = SeamAnchorCandidates(_canonical(document))
        if result.sha256 != seam_anchor_candidates_sha256(result.document):
            raise SeamAnchorCandidateError(
                "Seam anchor candidate canonical identity is inconsistent"
            )
        return result
    except SeamAnchorCandidateError:
        raise
    except (
        KeyError, OverflowError, RecursionError,
        SeamAnchorCandidateGeometryError,
        SeamAnchorCandidateValidationError, SeamAnchorInputError,
        TypeError, UnicodeError, ValueError,
    ) as exc:
        raise SeamAnchorCandidateError(
            f"Seam anchor candidate compilation failed: {exc}"
        ) from exc


def _copy(value: Any) -> Any:
    return json.loads(_canonical(value))


def _canonical(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    )
