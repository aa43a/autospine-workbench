"""Pure immutable five-file contract for MotionInstance v3 Spine exports."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import hashlib
from typing import Any

from .manifest_artifacts import (
    LayerManifestError,
    require_safe_token,
    require_sha256,
)
from .spine42_contract_v3 import (
    Spine42V3InputBindings,
    spine42_target_profile_v3_sha256,
)
from .spine42_export_validation import (
    MAX_ATLAS_BYTES,
    MAX_ATLAS_PNG_BYTES,
    MAX_SKELETON_JSON_BYTES,
    Spine42ExportValidationError,
    validate_spine42_export,
)
from .spine42_v3_export_evidence import (
    BUNDLE_INVENTORY,
    MAX_EXPORT_REPORT_BYTES,
    MAX_RUN_MANIFEST_BYTES,
    Spine42V3ExportEvidenceError,
    build_spine42_v3_export_evidence,
)
from .spine42_v3_document_validation import (
    Spine42V3DocumentValidationError,
    require_spine42_v3_document,
)
from .spine42_json_adapter_v3 import spine42_skeleton_hash_v3


DOCUMENT_NAMES = BUNDLE_INVENTORY
DOCUMENT_LIMITS = (
    MAX_SKELETON_JSON_BYTES, MAX_ATLAS_BYTES, MAX_ATLAS_PNG_BYTES,
    MAX_RUN_MANIFEST_BYTES, MAX_EXPORT_REPORT_BYTES,
)
MAX_TOTAL_DOCUMENT_BYTES = sum(DOCUMENT_LIMITS)
BUNDLE_ADDRESS_DOMAIN = b"autospine-spine42-v3-export-bundle-address/v1"
_P3_FIELDS = ("rig_sha256", "bundle_sha256")
_V3_FIELDS = (
    "motion_instance_v3_sha256", "bundle_sha256", "admission_sha256",
    "profile_sha256", "target_profile_sha256",
)


class Spine42V3BundleContractError(ValueError):
    """Raised when v3 export bytes or exact source identities disagree."""


@dataclass(frozen=True, slots=True)
class Spine42V3BundleContract:
    project_id: str
    clip_id: str
    adapter_profile_sha256: str
    p3_rig_sha256: str
    p3_bundle_sha256: str
    motion_instance_v3_sha256: str
    motion_instance_v3_bundle_sha256: str
    admission_sha256: str
    motion_instance_v3_profile_sha256: str
    target_profile_sha256: str
    skeleton_json_sha256: str
    atlas_sha256: str
    png_sha256: str
    run_identity_sha256: str
    run_document_sha256: str
    report_sha256: str
    bundle_sha256: str
    _source_images: tuple[tuple[str, str], ...] = field(repr=False)
    _documents: tuple[tuple[str, bytes], ...] = field(repr=False)

    @property
    def source_image_sha256s(self) -> dict[str, str]:
        return dict(self._source_images)

    @property
    def document_bytes(self) -> dict[str, bytes]:
        return dict(self._documents)

    @property
    def inventory(self) -> tuple[str, ...]:
        return tuple(name for name, _data in self._documents)

    @property
    def identities(self) -> dict[str, str]:
        return {
            "adapter_profile_sha256": self.adapter_profile_sha256,
            "p3_rig_sha256": self.p3_rig_sha256,
            "p3_bundle_sha256": self.p3_bundle_sha256,
            "motion_instance_v3_sha256": self.motion_instance_v3_sha256,
            "motion_instance_v3_bundle_sha256":
                self.motion_instance_v3_bundle_sha256,
            "admission_sha256": self.admission_sha256,
            "motion_instance_v3_profile_sha256":
                self.motion_instance_v3_profile_sha256,
            "target_profile_sha256": self.target_profile_sha256,
            "skeleton_json_sha256": self.skeleton_json_sha256,
            "atlas_sha256": self.atlas_sha256,
            "png_sha256": self.png_sha256,
            "run_identity_sha256": self.run_identity_sha256,
            "run_document_sha256": self.run_document_sha256,
            "report_sha256": self.report_sha256,
            "bundle_sha256": self.bundle_sha256,
        }


def build_spine42_v3_bundle_contract(
    project_id: str,
    clip_id: str,
    p3_source: Mapping[str, Any],
    motion_instance_v3_source: Mapping[str, Any],
    skeleton_json: Mapping[str, Any],
    atlas_bytes: bytes,
    png_bytes: bytes,
    source_image_sha256s: Mapping[str, str],
) -> Spine42V3BundleContract:
    """Validate the export, build evidence, and freeze its exact bytes."""

    try:
        project = require_safe_token(project_id, "Project id")
        clip = require_safe_token(clip_id, "Clip id")
        p3 = _source_identity(p3_source, _P3_FIELDS, "P3")
        motion = _source_identity(
            motion_instance_v3_source, _V3_FIELDS, "MotionInstance v3"
        )
        adapter_profile_sha = spine42_target_profile_v3_sha256()
        expected_hash = spine42_skeleton_hash_v3(Spine42V3InputBindings(
            adapter_profile_sha, p3["rig_sha256"],
            motion["motion_instance_v3_sha256"], motion["bundle_sha256"],
            motion["profile_sha256"], motion["target_profile_sha256"],
        ))
        require_spine42_v3_document(skeleton_json, clip_id=clip)
        validated = validate_spine42_export(
            skeleton_json, atlas_bytes, png_bytes, source_image_sha256s,
            expected_skeleton_hash=expected_hash, clip_id=clip,
        )
        outputs = {
            "skeleton_json_sha256": _sha(validated.skeleton_json_bytes),
            "atlas_sha256": _sha(validated.atlas_bytes),
            "png_sha256": _sha(validated.png_bytes),
        }
        evidence = build_spine42_v3_export_evidence(
            project, clip, p3, motion, outputs, validated
        )
        items = _require_items((
            (DOCUMENT_NAMES[0], validated.skeleton_json_bytes),
            (DOCUMENT_NAMES[1], validated.atlas_bytes),
            (DOCUMENT_NAMES[2], validated.png_bytes),
            (DOCUMENT_NAMES[3], evidence.run_bytes),
            (DOCUMENT_NAMES[4], evidence.report_bytes),
        ))
        skeleton_sha = outputs["skeleton_json_sha256"]
        return Spine42V3BundleContract(
            project, clip, adapter_profile_sha,
            p3["rig_sha256"], p3["bundle_sha256"],
            motion["motion_instance_v3_sha256"], motion["bundle_sha256"],
            motion["admission_sha256"], motion["profile_sha256"],
            motion["target_profile_sha256"], skeleton_sha,
            outputs["atlas_sha256"], outputs["png_sha256"],
            evidence.run_identity_sha256, evidence.run_document_sha256,
            evidence.report_sha256,
            spine42_v3_bundle_address_sha256(project, skeleton_sha, items),
            validated.source_images, items,
        )
    except Spine42V3BundleContractError:
        raise
    except (
        LayerManifestError, Spine42ExportValidationError,
        Spine42V3DocumentValidationError,
        Spine42V3ExportEvidenceError, KeyError, OverflowError,
        TypeError, UnicodeError, ValueError,
    ) as exc:
        raise Spine42V3BundleContractError(
            f"Spine 4.2 v3 bundle contract failed: {exc}"
        ) from exc


def spine42_v3_bundle_address_sha256(
    project_id: str,
    skeleton_json_sha256: str,
    document_items: tuple[tuple[str, bytes], ...],
) -> str:
    """Address the exact ordered five-file v3 export in its own domain."""

    try:
        project = require_safe_token(project_id, "Project id")
        skeleton_sha = require_sha256(
            skeleton_json_sha256, "Skeleton JSON SHA-256"
        )
        items = _require_items(document_items)
        if _sha(items[0][1]) != skeleton_sha:
            raise Spine42V3BundleContractError(
                "Skeleton JSON content differs from its address"
            )
        digest = hashlib.sha256()
        _feed(digest, BUNDLE_ADDRESS_DOMAIN)
        _feed(digest, project.encode("utf-8"))
        _feed(digest, skeleton_sha.encode("ascii"))
        digest.update(len(items).to_bytes(4, "big"))
        for name, data in items:
            _feed(digest, name.encode("ascii"))
            _feed(digest, data)
        return digest.hexdigest()
    except Spine42V3BundleContractError:
        raise
    except (LayerManifestError, OverflowError, TypeError, ValueError) as exc:
        raise Spine42V3BundleContractError(
            "Spine v3 bundle address inputs are invalid"
        ) from exc


def _source_identity(value: Any, fields: tuple[str, ...], label: str):
    if type(value) is not dict or set(value) != set(fields):
        raise Spine42V3BundleContractError(
            f"{label} source identity is invalid"
        )
    return {
        field: require_sha256(value[field], f"{label} {field}")
        for field in fields
    }


def _require_items(value: Any) -> tuple[tuple[str, bytes], ...]:
    if type(value) is not tuple or len(value) != len(DOCUMENT_NAMES):
        raise Spine42V3BundleContractError("Spine v3 bundle inventory is invalid")
    result = []
    for index, item in enumerate(value):
        if type(item) is not tuple or len(item) != 2:
            raise Spine42V3BundleContractError(
                "Spine v3 bundle inventory is invalid"
            )
        name, data = item
        if name != DOCUMENT_NAMES[index] or type(data) is not bytes \
                or len(data) > DOCUMENT_LIMITS[index]:
            raise Spine42V3BundleContractError(
                "Spine v3 bundle inventory is invalid"
            )
        result.append((name, data))
    if sum(len(data) for _name, data in result) > MAX_TOTAL_DOCUMENT_BYTES:
        raise Spine42V3BundleContractError("Spine v3 bundle byte limit exceeded")
    return tuple(result)


def _feed(digest, value: bytes) -> None:
    digest.update(len(value).to_bytes(8, "big"))
    digest.update(value)


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


__all__ = [
    "BUNDLE_ADDRESS_DOMAIN", "DOCUMENT_LIMITS", "DOCUMENT_NAMES",
    "MAX_TOTAL_DOCUMENT_BYTES", "Spine42V3BundleContract",
    "Spine42V3BundleContractError", "build_spine42_v3_bundle_contract",
    "spine42_v3_bundle_address_sha256",
]
