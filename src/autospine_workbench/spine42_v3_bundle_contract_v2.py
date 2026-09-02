"""Pure five-file P10.7a contract for P10.6b v2 sources."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import hashlib
from typing import Any

from .manifest_artifacts import (
    LayerManifestError, require_safe_token, require_sha256,
)
from .spine42_contract_v3_v2 import (
    MOTION_SOURCE_FIELDS, Spine42V3InputBindingsV2,
    spine42_motion_source_v3_v2_sha256,
    spine42_source_contract_v3_v2_sha256,
    spine42_target_profile_v3_v2_sha256,
)
from .spine42_export_validation import (
    MAX_ATLAS_BYTES, MAX_ATLAS_PNG_BYTES, MAX_SKELETON_JSON_BYTES,
    Spine42ExportValidationError, validate_spine42_export,
)
from .spine42_json_adapter_v3_v2 import spine42_skeleton_hash_v3_v2
from .spine42_v3_document_validation import (
    Spine42V3DocumentValidationError, require_spine42_v3_document,
)
from .spine42_v3_export_evidence_v2 import (
    BUNDLE_INVENTORY, MAX_EXPORT_REPORT_BYTES, MAX_RUN_MANIFEST_BYTES,
    Spine42V3ExportEvidenceV2Error,
    build_spine42_v3_export_evidence_v2,
)

DOCUMENT_NAMES = BUNDLE_INVENTORY
DOCUMENT_LIMITS = (
    MAX_SKELETON_JSON_BYTES, MAX_ATLAS_BYTES, MAX_ATLAS_PNG_BYTES,
    MAX_RUN_MANIFEST_BYTES, MAX_EXPORT_REPORT_BYTES,
)
MAX_TOTAL_DOCUMENT_BYTES = sum(DOCUMENT_LIMITS)
BUNDLE_ADDRESS_DOMAIN = b"autospine-spine42-v3-export-bundle-address/v2"
_P3_FIELDS = ("rig_sha256", "bundle_sha256")


class Spine42V3BundleContractV2Error(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Spine42V3BundleContractV2:
    project_id: str
    clip_id: str
    adapter_profile_sha256: str
    source_contract_sha256: str
    motion_instance_v3_source_sha256: str
    p3_rig_sha256: str
    p3_bundle_sha256: str
    motion_instance_v3_sha256: str
    motion_instance_v3_bundle_sha256: str
    admission_sha256: str
    source_set_sha256: str
    source_document_sha256: str
    dynamic_seam_probe_sha256: str
    dynamic_seam_bundle_sha256: str
    motion_instance_v2_sha256: str
    reviewed_motion_bundle_sha256: str
    motion_instance_v3_profile_sha256: str
    motion_domain_sha256: str
    rotation_timeline_sha256: str
    base_channels_sha256: str
    rig_ir_sha256: str
    target_profile_sha256: str
    motion_instance_v3_run_sha256: str
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
    def source_image_sha256s(self):
        return dict(self._source_images)

    @property
    def document_bytes(self):
        return dict(self._documents)

    @property
    def inventory(self):
        return tuple(name for name, _data in self._documents)

    @property
    def p3_source(self):
        return {"rig_sha256": self.p3_rig_sha256,
                "bundle_sha256": self.p3_bundle_sha256}

    @property
    def motion_instance_v3_source(self):
        values = (
            self.motion_instance_v3_sha256,
            self.motion_instance_v3_bundle_sha256,
            self.admission_sha256, self.source_set_sha256,
            self.source_document_sha256, self.dynamic_seam_probe_sha256,
            self.dynamic_seam_bundle_sha256,
            self.motion_instance_v2_sha256,
            self.reviewed_motion_bundle_sha256,
            self.motion_instance_v3_profile_sha256,
            self.motion_domain_sha256, self.rotation_timeline_sha256,
            self.base_channels_sha256, self.rig_ir_sha256,
            self.target_profile_sha256, self.motion_instance_v3_run_sha256,
        )
        return dict(zip(MOTION_SOURCE_FIELDS, values, strict=True))

    @property
    def identities(self):
        names = (
            "adapter_profile_sha256", "source_contract_sha256",
            "motion_instance_v3_source_sha256", "p3_rig_sha256",
            "p3_bundle_sha256", "motion_instance_v3_sha256",
            "motion_instance_v3_bundle_sha256", "admission_sha256",
            "source_set_sha256", "source_document_sha256",
            "dynamic_seam_probe_sha256", "dynamic_seam_bundle_sha256",
            "motion_instance_v2_sha256", "reviewed_motion_bundle_sha256",
            "motion_instance_v3_profile_sha256", "motion_domain_sha256",
            "rotation_timeline_sha256", "base_channels_sha256",
            "rig_ir_sha256", "target_profile_sha256",
            "motion_instance_v3_run_sha256",
            "skeleton_json_sha256", "atlas_sha256", "png_sha256",
            "run_identity_sha256", "run_document_sha256",
            "report_sha256", "bundle_sha256",
        )
        return {name: getattr(self, name) for name in names}


def build_spine42_v3_bundle_contract_v2(
    project_id: str, clip_id: str, p3_source: Mapping[str, Any],
    motion_instance_v3_source: Mapping[str, Any],
    skeleton_json: Mapping[str, Any], atlas_bytes: bytes, png_bytes: bytes,
    source_image_sha256s: Mapping[str, str],
) -> Spine42V3BundleContractV2:
    """Validate deterministic adapter bytes and freeze their v2 identity."""

    try:
        project = require_safe_token(project_id, "Project id")
        clip = require_safe_token(clip_id, "Clip id")
        p3 = _source_identity(p3_source, _P3_FIELDS, "P3")
        motion = _source_identity(
            motion_instance_v3_source, MOTION_SOURCE_FIELDS,
            "P10.6b v2 MotionInstance v3",
        )
        if p3["rig_sha256"] != motion["rig_ir_sha256"]:
            raise Spine42V3BundleContractV2Error(
                "P10.7a v2 P3 rig differs from MotionInstance v3"
            )
        adapter_sha = spine42_target_profile_v3_v2_sha256()
        source_contract_sha = spine42_source_contract_v3_v2_sha256()
        source_sha = spine42_motion_source_v3_v2_sha256(motion)
        bindings = Spine42V3InputBindingsV2(
            adapter_sha, source_contract_sha, source_sha,
            p3["rig_sha256"], motion["motion_instance_v3_sha256"],
            motion["bundle_sha256"],
            motion["motion_instance_v3_profile_sha256"],
            motion["target_profile_sha256"],
        )
        require_spine42_v3_document(skeleton_json, clip_id=clip)
        validated = validate_spine42_export(
            skeleton_json, atlas_bytes, png_bytes, source_image_sha256s,
            expected_skeleton_hash=spine42_skeleton_hash_v3_v2(bindings),
            clip_id=clip,
        )
        outputs = {
            "skeleton_json_sha256": _sha(validated.skeleton_json_bytes),
            "atlas_sha256": _sha(validated.atlas_bytes),
            "png_sha256": _sha(validated.png_bytes),
        }
        evidence = build_spine42_v3_export_evidence_v2(
            project, clip, p3, motion, outputs, validated,
        )
        items = _require_items((
            (DOCUMENT_NAMES[0], validated.skeleton_json_bytes),
            (DOCUMENT_NAMES[1], validated.atlas_bytes),
            (DOCUMENT_NAMES[2], validated.png_bytes),
            (DOCUMENT_NAMES[3], evidence.run_bytes),
            (DOCUMENT_NAMES[4], evidence.report_bytes),
        ))
        values = (
            project, clip, adapter_sha, source_contract_sha, source_sha,
            p3["rig_sha256"], p3["bundle_sha256"],
            *(motion[name] for name in MOTION_SOURCE_FIELDS),
            outputs["skeleton_json_sha256"], outputs["atlas_sha256"],
            outputs["png_sha256"], evidence.run_identity_sha256,
            evidence.run_document_sha256, evidence.report_sha256,
        )
        bundle_sha = spine42_v3_bundle_address_sha256_v2(
            project, outputs["skeleton_json_sha256"], items,
        )
        return Spine42V3BundleContractV2(
            *values, bundle_sha, validated.source_images, items,
        )
    except Spine42V3BundleContractV2Error:
        raise
    except (
        LayerManifestError, Spine42ExportValidationError,
        Spine42V3DocumentValidationError, Spine42V3ExportEvidenceV2Error,
        KeyError, OverflowError, TypeError, UnicodeError, ValueError,
    ) as exc:
        raise Spine42V3BundleContractV2Error(
            f"Spine 4.2 v2-source bundle contract failed: {exc}"
        ) from exc


def spine42_v3_bundle_address_sha256_v2(
    project_id, skeleton_json_sha256, document_items,
):
    try:
        project = require_safe_token(project_id, "Project id")
        skeleton_sha = require_sha256(
            skeleton_json_sha256, "Skeleton JSON SHA-256",
        )
        items = _require_items(document_items)
        if _sha(items[0][1]) != skeleton_sha:
            raise Spine42V3BundleContractV2Error(
                "Skeleton bytes differ from their v2 address"
            )
        digest = hashlib.sha256()
        for value in (
            BUNDLE_ADDRESS_DOMAIN, project.encode(), skeleton_sha.encode(),
        ):
            _feed(digest, value)
        digest.update(len(items).to_bytes(4, "big"))
        for name, data in items:
            _feed(digest, name.encode("ascii"))
            _feed(digest, data)
        return digest.hexdigest()
    except Spine42V3BundleContractV2Error:
        raise
    except (LayerManifestError, OverflowError, TypeError, ValueError) as exc:
        raise Spine42V3BundleContractV2Error(
            "P10.7a v2 bundle address inputs are invalid"
        ) from exc


def _source_identity(value, fields, label):
    if type(value) is not dict or set(value) != set(fields):
        raise Spine42V3BundleContractV2Error(
            f"{label} source identity is invalid"
        )
    return {name: require_sha256(value[name], f"{label} {name}")
            for name in fields}


def _require_items(value):
    if type(value) is not tuple or len(value) != len(DOCUMENT_NAMES):
        raise Spine42V3BundleContractV2Error(
            "P10.7a v2 bundle inventory is invalid"
        )
    result = []
    for index, item in enumerate(value):
        if type(item) is not tuple or len(item) != 2 \
                or item[0] != DOCUMENT_NAMES[index] \
                or type(item[1]) is not bytes \
                or len(item[1]) > DOCUMENT_LIMITS[index]:
            raise Spine42V3BundleContractV2Error(
                "P10.7a v2 bundle inventory is invalid"
            )
        result.append(item)
    if sum(len(data) for _name, data in result) > MAX_TOTAL_DOCUMENT_BYTES:
        raise Spine42V3BundleContractV2Error(
            "P10.7a v2 bundle byte limit exceeded"
        )
    return tuple(result)


def _feed(digest, value):
    digest.update(len(value).to_bytes(8, "big"))
    digest.update(value)


def _sha(value):
    return hashlib.sha256(value).hexdigest()


__all__ = [
    "BUNDLE_ADDRESS_DOMAIN", "DOCUMENT_LIMITS", "DOCUMENT_NAMES",
    "MAX_TOTAL_DOCUMENT_BYTES", "Spine42V3BundleContractV2",
    "Spine42V3BundleContractV2Error",
    "build_spine42_v3_bundle_contract_v2",
    "spine42_v3_bundle_address_sha256_v2",
]
