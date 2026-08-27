"""Exact static-source address for one P10.5b seam-anchor review."""

from __future__ import annotations

from dataclasses import dataclass

from .manifest_artifacts import (
    LayerManifestError,
    require_safe_token,
    require_sha256,
)


class ExactSeamAnchorReviewAddressError(ValueError):
    """Raised when a seam review source address is not exact and portable."""


@dataclass(frozen=True, slots=True)
class ExactSeamAnchorReviewAddress:
    """Address immutable Layer Manifest and P3 bundle inputs without discovery."""

    project_id: str
    layer_manifest_sha256: str
    p3_rig_sha256: str
    p3_bundle_sha256: str

    def __post_init__(self) -> None:
        try:
            require_safe_token(self.project_id, "Seam review project id")
            require_sha256(
                self.layer_manifest_sha256,
                "Seam review Layer Manifest digest",
            )
            require_sha256(self.p3_rig_sha256, "Seam review P3 rig digest")
            require_sha256(
                self.p3_bundle_sha256, "Seam review P3 bundle digest"
            )
        except LayerManifestError as exc:
            raise ExactSeamAnchorReviewAddressError(
                "Seam-anchor review source address is invalid"
            ) from exc

    @property
    def manifest_reader_arguments(self) -> tuple[str, str]:
        return self.project_id, self.layer_manifest_sha256

    @property
    def mesh_reader_arguments(self) -> tuple[str, str, str]:
        return self.project_id, self.p3_rig_sha256, self.p3_bundle_sha256

    def public_document(self) -> dict[str, str]:
        """Return the path-free exact source identity for adapters."""

        return {
            "project_id": self.project_id,
            "layer_manifest_sha256": self.layer_manifest_sha256,
            "p3_rig_sha256": self.p3_rig_sha256,
            "p3_bundle_sha256": self.p3_bundle_sha256,
        }
