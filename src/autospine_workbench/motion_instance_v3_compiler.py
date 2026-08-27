"""Pure compilation of a P10.6a admission into MotionInstance v3."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import hashlib
import json
from typing import Any

from .body_sway_motion_consumer_p9 import (
    BodySwayMotionConsumerP9Error,
    require_verified_reviewed_motion_bundle,
)
from .body_sway_motion_consumer_validation import (
    BodySwayMotionConsumerAdmissionValidationError,
    body_sway_motion_consumer_admission_canonical_bytes,
)
from .motion_instance_v3_contract import (
    MotionInstanceV3ContractError,
    build_motion_instance_v3_document,
)
from .motion_instance_v3_validation import (
    MotionInstanceV3ValidationError,
    require_motion_instance_v3,
)
from .reviewed_motion_bundle_integrity import VerifiedReviewedMotionBundle
from .seam_anchor_review_json import canonical_json_bytes


class MotionInstanceV3CompilerError(ValueError):
    """Raised when exact P10.6a/P9 inputs cannot form MotionInstance v3."""


@dataclass(frozen=True, slots=True)
class MotionInstanceV3:
    """Frozen canonical v3 value with isolated document access."""

    _canonical_json: str = field(repr=False)

    @property
    def document(self) -> dict[str, Any]:
        return json.loads(self._canonical_json)

    @property
    def canonical_bytes(self) -> bytes:
        return self._canonical_json.encode("utf-8")

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes).hexdigest()


def compile_motion_instance_v3(
    admission: Mapping[str, Any],
    reviewed_bundle: VerifiedReviewedMotionBundle,
) -> MotionInstanceV3:
    """Compile exact sampled rotations and unchanged MIv2 base channels."""

    try:
        admission_bytes = body_sway_motion_consumer_admission_canonical_bytes(
            admission, reviewed_bundle=reviewed_bundle
        )
        admitted = json.loads(admission_bytes)
        motion = require_verified_reviewed_motion_bundle(
            reviewed_bundle, admitted["source"]["p9"]
        )
        document = build_motion_instance_v3_document(
            admitted,
            motion,
            admission_sha256=hashlib.sha256(admission_bytes).hexdigest(),
            p9_bundle_sha256=reviewed_bundle.bundle_sha256,
        )
        require_motion_instance_v3(
            document, admission=admitted, reviewed_bundle=reviewed_bundle
        )
        canonical = canonical_json_bytes(document)
        return MotionInstanceV3(canonical.decode("utf-8"))
    except MotionInstanceV3CompilerError:
        raise
    except (
        BodySwayMotionConsumerAdmissionValidationError,
        BodySwayMotionConsumerP9Error, MotionInstanceV3ContractError,
        MotionInstanceV3ValidationError, AttributeError, KeyError,
        OverflowError, TypeError, UnicodeError, ValueError,
    ) as exc:
        raise MotionInstanceV3CompilerError(
            f"MotionInstance v3 compilation failed: {exc}"
        ) from exc


__all__ = [
    "MotionInstanceV3", "MotionInstanceV3CompilerError",
    "compile_motion_instance_v3",
]
