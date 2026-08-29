"""Content identity for one adopted P9 chain entering idle review."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

from .manifest_artifacts import (
    LayerManifestError,
    require_safe_token,
    require_sha256,
)


class IdleBehaviorReviewAddressError(ValueError):
    """Raised when an idle-review address is incomplete or malformed."""


@dataclass(frozen=True, slots=True)
class IdleBehaviorReviewAddress:
    """Exact package/P9 identity; never resolve a latest alias."""

    motion_policy_package_id: str
    project_id: str
    motion_id: str
    clip_id: str
    motion_instance_v2_sha256: str
    reviewed_motion_bundle_sha256: str
    p9_decision_sha256: str

    def __post_init__(self) -> None:
        try:
            object.__setattr__(
                self, "motion_policy_package_id",
                require_sha256(
                    self.motion_policy_package_id,
                    "Motion-policy package digest",
                ),
            )
            for field in ("project_id", "motion_id", "clip_id"):
                object.__setattr__(
                    self, field,
                    require_safe_token(getattr(self, field), field),
                )
            for field in (
                "motion_instance_v2_sha256",
                "reviewed_motion_bundle_sha256",
                "p9_decision_sha256",
            ):
                object.__setattr__(
                    self, field,
                    require_sha256(getattr(self, field), field),
                )
        except (LayerManifestError, TypeError, ValueError) as exc:
            raise IdleBehaviorReviewAddressError(
                "Idle behavior review address is invalid"
            ) from exc

    @property
    def package_id(self) -> str:
        payload = json.dumps(
            {
                "domain": "autospine-idle-behavior-review-package-id/v1",
                **self.public_document(),
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def public_document(self) -> dict[str, str]:
        return {
            "motion_policy_package_id": self.motion_policy_package_id,
            "project_id": self.project_id,
            "motion_id": self.motion_id,
            "clip_id": self.clip_id,
            "motion_instance_v2_sha256": self.motion_instance_v2_sha256,
            "reviewed_motion_bundle_sha256": (
                self.reviewed_motion_bundle_sha256
            ),
            "p9_decision_sha256": self.p9_decision_sha256,
        }
