"""Authoritative exact-source replay for P10.5b seam review."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .manifest_bundle import (
    LayerManifestBundleError,
    LayerManifestBundleReader,
)
from .mesh_bundle_integrity import VerifiedMeshBundle
from .mesh_bundle_reader import (
    VerifiedMeshBundleReader,
    VerifiedMeshBundleReaderError,
)
from .seam_anchor_candidates import (
    SeamAnchorCandidateError,
    SeamAnchorCandidates,
    compile_seam_anchor_candidates,
)
from .seam_anchor_review_address import ExactSeamAnchorReviewAddress


class SeamAnchorReviewCandidateBindingError(RuntimeError):
    """Raised when exact static inputs cannot reproduce current candidates."""


@dataclass(frozen=True, slots=True)
class BoundSeamAnchorReviewCandidate:
    """Fresh candidate plus the exact P3 value needed for adjusted locators."""

    candidates: SeamAnchorCandidates
    mesh_bundle: VerifiedMeshBundle


def load_bound_seam_anchor_review_candidate(
    state_root: Path,
    address: ExactSeamAnchorReviewAddress,
) -> BoundSeamAnchorReviewCandidate:
    """Replay exact Layer Manifest/P3 inputs and compile without discovery."""

    try:
        if type(address) is not ExactSeamAnchorReviewAddress:
            raise SeamAnchorReviewCandidateBindingError(
                "Seam review requires an exact static-source address"
            )
        state = Path(state_root)
        manifest = LayerManifestBundleReader(state).load(
            *address.manifest_reader_arguments
        )
        mesh = VerifiedMeshBundleReader(state).load(
            *address.mesh_reader_arguments
        )
        candidates = compile_seam_anchor_candidates(
            manifest.manifest, mesh
        )
        source = candidates.document["source"]
        if source["layer_manifest_sha256"] != address.layer_manifest_sha256 \
                or source["rig_sha256"] != address.p3_rig_sha256 \
                or source["bundle_sha256"] != address.p3_bundle_sha256:
            raise SeamAnchorReviewCandidateBindingError(
                "Compiled seam candidate source differs from its address"
            )
        return BoundSeamAnchorReviewCandidate(candidates, mesh)
    except SeamAnchorReviewCandidateBindingError:
        raise
    except (
        AttributeError, KeyError, LayerManifestBundleError,
        OSError, OverflowError, RecursionError, RuntimeError,
        SeamAnchorCandidateError, TypeError, UnicodeError, ValueError,
        VerifiedMeshBundleReaderError,
    ) as exc:
        raise SeamAnchorReviewCandidateBindingError(
            "Exact seam-review candidate replay failed"
        ) from exc
