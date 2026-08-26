"""Exact four-part address for one P10.3c visual-review source."""

from __future__ import annotations

from dataclasses import dataclass

from .manifest_artifacts import (
    LayerManifestError,
    require_safe_token,
    require_sha256,
)


class ExactVisualReviewAddressError(ValueError):
    """Raised when a visual review source address is not exact and portable."""


@dataclass(frozen=True, slots=True)
class ExactVisualReviewAddress:
    """Address one immutable capture without discovery or latest aliases."""

    project_id: str
    temporary_preview_sha256: str
    runtime_capture_bundle_sha256: str
    capture_artifact_set_sha256: str

    def __post_init__(self) -> None:
        try:
            require_safe_token(self.project_id, "Visual review project id")
            require_sha256(
                self.temporary_preview_sha256,
                "Visual review temporary preview digest",
            )
            require_sha256(
                self.runtime_capture_bundle_sha256,
                "Visual review runtime capture bundle digest",
            )
            require_sha256(
                self.capture_artifact_set_sha256,
                "Visual review capture artifact-set digest",
            )
        except LayerManifestError as exc:
            raise ExactVisualReviewAddressError(
                "Visual review source address is invalid"
            ) from exc

    @property
    def reader_arguments(self) -> tuple[str, str, str, str]:
        """Return the exact order expected by the immutable capture reader."""

        return (
            self.project_id,
            self.temporary_preview_sha256,
            self.runtime_capture_bundle_sha256,
            self.capture_artifact_set_sha256,
        )

    def public_document(self) -> dict[str, str]:
        """Return a bounded path-free identity suitable for APIs and CLIs."""

        return {
            "project_id": self.project_id,
            "temporary_preview_sha256": self.temporary_preview_sha256,
            "runtime_capture_bundle_sha256":
                self.runtime_capture_bundle_sha256,
            "capture_artifact_set_sha256":
                self.capture_artifact_set_sha256,
        }
