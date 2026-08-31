"""Exact four-part address for one P10.3c v2 execution source."""

from __future__ import annotations

from dataclasses import dataclass

from .manifest_artifacts import (
    LayerManifestError,
    require_safe_token,
    require_sha256,
)


class ExactVisualReviewAddressV2Error(ValueError):
    """Raised when a v2 execution address is unsafe or incomplete."""


@dataclass(frozen=True, slots=True)
class ExactVisualReviewAddressV2:
    project_id: str
    temporary_preview_v2_sha256: str
    runtime_execution_bundle_sha256: str
    capture_artifact_set_sha256: str

    def __post_init__(self) -> None:
        try:
            require_safe_token(self.project_id, "Visual review v2 project")
            require_sha256(
                self.temporary_preview_v2_sha256,
                "Visual review v2 preview",
            )
            require_sha256(
                self.runtime_execution_bundle_sha256,
                "Visual review v2 execution bundle",
            )
            require_sha256(
                self.capture_artifact_set_sha256,
                "Visual review v2 capture artifact set",
            )
        except LayerManifestError as exc:
            raise ExactVisualReviewAddressV2Error(
                "Visual review v2 source address is invalid"
            ) from exc

    @property
    def reader_arguments(self) -> tuple[str, str, str, str]:
        return (
            self.project_id,
            self.temporary_preview_v2_sha256,
            self.runtime_execution_bundle_sha256,
            self.capture_artifact_set_sha256,
        )

    def public_document(self) -> dict[str, str]:
        return {
            "project_id": self.project_id,
            "temporary_preview_v2_sha256":
                self.temporary_preview_v2_sha256,
            "runtime_execution_bundle_sha256":
                self.runtime_execution_bundle_sha256,
            "capture_artifact_set_sha256":
                self.capture_artifact_set_sha256,
        }


__all__ = ["ExactVisualReviewAddressV2", "ExactVisualReviewAddressV2Error"]
