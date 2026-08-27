"""Pure immutable three-document contract for MotionInstance v3."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import hashlib
from typing import Any

from .body_sway_motion_consumer_validation import (
    BodySwayMotionConsumerAdmissionValidationError,
    body_sway_motion_consumer_admission_canonical_bytes,
)
from .manifest_artifacts import LayerManifestError, require_safe_token
from .motion_instance_v3_bundle_run import (
    MAX_RUN_BYTES,
    MotionInstanceV3BundleRunError,
    build_motion_instance_v3_bundle_run,
)
from .motion_instance_v3_compiler import (
    MotionInstanceV3CompilerError,
    compile_motion_instance_v3,
)
from .motion_instance_v3_validation import (
    MAX_DOCUMENT_BYTES as MAX_INSTANCE_V3_BYTES,
)
from .reviewed_motion_bundle_integrity import VerifiedReviewedMotionBundle
from .seam_anchor_review_json import canonical_json_bytes


BUNDLE_ADDRESS_DOMAIN = (
    b"autospine-body-sway-motion-instance-v3-bundle-address/v1"
)
MAX_ADMISSION_BYTES = 64 * 1024 * 1024
DOCUMENT_NAMES = (
    "body-sway-motion-consumer-admission.json",
    "motion-instance-v3.json",
    "run-manifest.json",
)
DOCUMENT_LIMITS = (
    MAX_ADMISSION_BYTES,
    MAX_INSTANCE_V3_BYTES,
    MAX_RUN_BYTES,
)
MAX_TOTAL_DOCUMENT_BYTES = sum(DOCUMENT_LIMITS)


class MotionInstanceV3BundleContractError(ValueError):
    """Raised when proposed bundle documents cannot be reproduced exactly."""


@dataclass(frozen=True, slots=True)
class MotionInstanceV3BundleContract:
    """Frozen canonical documents and their domain-separated address."""

    project_id: str
    clip_id: str
    admission_sha256: str
    motion_instance_v2_sha256: str
    reviewed_motion_bundle_sha256: str
    motion_instance_v3_sha256: str
    motion_instance_v3_profile_sha256: str
    motion_domain_sha256: str
    rotation_timeline_sha256: str
    base_channels_sha256: str
    rig_ir_sha256: str
    target_profile_sha256: str
    run_sha256: str
    bundle_sha256: str
    _documents: tuple[tuple[str, bytes], ...] = field(repr=False)

    @property
    def document_bytes(self) -> dict[str, bytes]:
        return dict(self._documents)

    @property
    def inventory(self) -> tuple[str, ...]:
        return tuple(name for name, _data in self._documents)

    @property
    def identities(self) -> dict[str, str]:
        return {
            "admission_sha256": self.admission_sha256,
            "motion_instance_v2_sha256": self.motion_instance_v2_sha256,
            "reviewed_motion_bundle_sha256":
                self.reviewed_motion_bundle_sha256,
            "motion_instance_v3_sha256": self.motion_instance_v3_sha256,
            "motion_instance_v3_profile_sha256":
                self.motion_instance_v3_profile_sha256,
            "motion_domain_sha256": self.motion_domain_sha256,
            "rotation_timeline_sha256": self.rotation_timeline_sha256,
            "base_channels_sha256": self.base_channels_sha256,
            "rig_ir_sha256": self.rig_ir_sha256,
            "target_profile_sha256": self.target_profile_sha256,
            "run_sha256": self.run_sha256,
            "bundle_sha256": self.bundle_sha256,
        }


def build_motion_instance_v3_bundle_contract(
    project_id: str,
    admission: Mapping[str, Any],
    motion_instance_v3: Mapping[str, Any],
    reviewed_bundle: VerifiedReviewedMotionBundle,
) -> MotionInstanceV3BundleContract:
    """Recompile v3, build its run, and freeze the exact three-file set."""

    try:
        project = require_safe_token(project_id, "Project id")
        admission_bytes = body_sway_motion_consumer_admission_canonical_bytes(
            admission, reviewed_bundle=reviewed_bundle
        )
        if len(admission_bytes) > MAX_ADMISSION_BYTES:
            raise MotionInstanceV3BundleContractError(
                f"{DOCUMENT_NAMES[0]} exceeds its byte limit"
            )
        admission_document = _json_object(admission, DOCUMENT_NAMES[0])
        if canonical_json_bytes(admission_document) != admission_bytes:
            raise MotionInstanceV3BundleContractError(
                "Admission bytes differ from canonical P10.6a replay"
            )
        compiled = compile_motion_instance_v3(
            admission_document, reviewed_bundle
        )
        supplied_v3 = _document(motion_instance_v3, 1)
        if supplied_v3 != compiled.canonical_bytes:
            raise MotionInstanceV3BundleContractError(
                "MotionInstance v3 differs from exact compilation"
            )
        if project != admission_document["project_id"] \
                or project != reviewed_bundle.project_id:
            raise MotionInstanceV3BundleContractError(
                "Bundle project differs from P10.6a or exact P9"
            )
        v3 = compiled.document
        source = v3["source"]
        admission_sha = hashlib.sha256(admission_bytes).hexdigest()
        if source["body_sway_motion_consumer_admission_sha256"] \
                != admission_sha:
            raise MotionInstanceV3BundleContractError(
                "MotionInstance v3 admission identity is inconsistent"
            )
        run = build_motion_instance_v3_bundle_run(
            project,
            v3["clip_id"],
            body_sway_motion_consumer_admission_sha256=admission_sha,
            p9=source["p9"],
            motion_domain_sha256=source["motion_domain_sha256"],
            rotation_timeline_sha256=source["rotation_timeline_sha256"],
            base_channels_sha256=source["base_channels_sha256"],
            rig_ir_sha256=source["rig_ir_sha256"],
            target_profile_sha256=source["target_profile_sha256"],
            motion_instance_v3_sha256=compiled.sha256,
            motion_instance_v3_profile_sha256=source[
                "motion_instance_v3_profile_sha256"
            ],
        )
        items = _require_items(tuple(zip(
            DOCUMENT_NAMES,
            (admission_bytes, supplied_v3, run.canonical_bytes),
            strict=True,
        )))
        bundle_sha = motion_instance_v3_bundle_address_sha256(
            project, compiled.sha256, items
        )
        return MotionInstanceV3BundleContract(
            project, v3["clip_id"], admission_sha,
            source["p9"]["motion_instance_v2_sha256"],
            source["p9"]["bundle_sha256"], compiled.sha256,
            source["motion_instance_v3_profile_sha256"],
            source["motion_domain_sha256"],
            source["rotation_timeline_sha256"],
            source["base_channels_sha256"], source["rig_ir_sha256"],
            source["target_profile_sha256"], run.sha256, bundle_sha, items,
        )
    except MotionInstanceV3BundleContractError:
        raise
    except (
        AttributeError, BodySwayMotionConsumerAdmissionValidationError,
        KeyError, LayerManifestError, MotionInstanceV3BundleRunError,
        MotionInstanceV3CompilerError, OverflowError, RecursionError,
        TypeError, UnicodeError, ValueError,
    ) as exc:
        raise MotionInstanceV3BundleContractError(
            f"MotionInstance v3 bundle contract failed: {exc}"
        ) from exc


def motion_instance_v3_bundle_address_sha256(
    project_id: str,
    motion_instance_v3_sha256: str,
    document_items: tuple[tuple[str, bytes], ...],
) -> str:
    """Hash project, v3 identity, and all ordered filename/byte frames."""

    try:
        project = require_safe_token(project_id, "Project id")
        _require_sha(motion_instance_v3_sha256, "MotionInstance v3")
        items = _require_items(document_items)
        if _sha(items[1][1]) != motion_instance_v3_sha256:
            raise MotionInstanceV3BundleContractError(
                "MotionInstance v3 bytes differ from their address"
            )
        digest = hashlib.sha256()
        _feed(digest, BUNDLE_ADDRESS_DOMAIN)
        _feed(digest, project.encode("utf-8"))
        _feed(digest, motion_instance_v3_sha256.encode("ascii"))
        digest.update(len(items).to_bytes(4, "big"))
        for name, data in items:
            _feed(digest, name.encode("ascii"))
            _feed(digest, data)
        return digest.hexdigest()
    except MotionInstanceV3BundleContractError:
        raise
    except (LayerManifestError, OverflowError, TypeError, ValueError) as exc:
        raise MotionInstanceV3BundleContractError(
            "MotionInstance v3 bundle address inputs are invalid"
        ) from exc


def _document(value: Mapping[str, Any], index: int) -> bytes:
    document = _json_object(value, DOCUMENT_NAMES[index])
    data = canonical_json_bytes(document)
    if len(data) > DOCUMENT_LIMITS[index]:
        raise MotionInstanceV3BundleContractError(
            f"{DOCUMENT_NAMES[index]} exceeds its byte limit"
        )
    return data


def _json_object(value: Any, label: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise MotionInstanceV3BundleContractError(
            f"{label} must be an exact JSON object"
        )
    return value


def _require_items(value) -> tuple[tuple[str, bytes], ...]:
    if type(value) is not tuple or len(value) != len(DOCUMENT_NAMES):
        raise MotionInstanceV3BundleContractError(
            "MotionInstance v3 bundle inventory is invalid"
        )
    result, total = [], 0
    for index, item in enumerate(value):
        if type(item) is not tuple or len(item) != 2 \
                or item[0] != DOCUMENT_NAMES[index] \
                or not isinstance(item[1], bytes):
            raise MotionInstanceV3BundleContractError(
                "MotionInstance v3 bundle inventory order or type is invalid"
            )
        total += len(item[1])
        if len(item[1]) > DOCUMENT_LIMITS[index]:
            raise MotionInstanceV3BundleContractError(
                f"{item[0]} exceeds its byte limit"
            )
        result.append(item)
    if total > MAX_TOTAL_DOCUMENT_BYTES:
        raise MotionInstanceV3BundleContractError(
            "MotionInstance v3 bundle exceeds its total byte limit"
        )
    return tuple(result)


def _require_sha(value: Any, label: str) -> None:
    if not isinstance(value, str) or len(value) != 64 \
            or any(char not in "0123456789abcdef" for char in value):
        raise MotionInstanceV3BundleContractError(f"{label} address is invalid")


def _feed(digest, value: bytes) -> None:
    digest.update(len(value).to_bytes(8, "big"))
    digest.update(value)


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


__all__ = [
    "DOCUMENT_LIMITS", "DOCUMENT_NAMES", "MAX_ADMISSION_BYTES",
    "MAX_TOTAL_DOCUMENT_BYTES",
    "MotionInstanceV3BundleContract", "MotionInstanceV3BundleContractError",
    "build_motion_instance_v3_bundle_contract",
    "motion_instance_v3_bundle_address_sha256",
]
