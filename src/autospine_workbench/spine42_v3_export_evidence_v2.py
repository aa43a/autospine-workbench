"""Canonical P10.7a v2-source run and structural evidence."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import hashlib
import json
from types import MappingProxyType
from typing import Any

from .spine42_contract_v3_v2 import (
    spine42_source_contract_v3_v2,
    spine42_source_contract_v3_v2_sha256,
    spine42_target_profile_v3_v2,
    spine42_target_profile_v3_v2_sha256,
)
from .spine42_export_validation import ValidatedSpine42Export

MAX_RUN_MANIFEST_BYTES = 2 * 1024 * 1024
MAX_EXPORT_REPORT_BYTES = 2 * 1024 * 1024
RUN_IDENTITY_DOMAIN = b"autospine-spine42-v3-export-run-identity/v2"
BUNDLE_INVENTORY = (
    "skeleton.json", "skeleton.atlas", "skeleton.png",
    "run-manifest.json", "export-report.json",
)
_EVIDENCE_PROFILE = {
    "id": "autospine-spine42-v3-export-evidence-v2",
    "version": "2.0.0",
    "canonicalization": "canonical-json-utf8-sort-keys-no-nonfinite",
    "bundle_inventory": list(BUNDLE_INVENTORY),
}
AUTHORITY = MappingProxyType({
    "spine_adapter_emitted": True,
    "attachment_area_overlap_assessed": False,
    "dynamic_seam_safety": False,
    "full_attachment_boundary_continuity": False,
    "official_runtime_loaded": False,
    "runtime_equivalence": False,
    "raster_visual_quality": False,
    "persistent_current_head_authority": False,
    "publishable_spine_timeline": False,
    "release_authority": False,
})
_REASONS = (
    "attachment_area_overlap_not_assessed",
    "dynamic_seam_safety_unproven",
    "full_attachment_boundary_continuity_unproven",
    "official_runtime_not_loaded",
    "persistent_current_head_authority_not_granted",
    "publishable_spine_timeline_not_granted",
    "raster_visual_quality_unproven",
    "release_authority_not_granted",
    "runtime_equivalence_unproven",
)
RELEASE_GATE = MappingProxyType({
    "status": "blocked", "reason_codes": _REASONS,
})


class Spine42V3ExportEvidenceV2Error(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Spine42V3ExportEvidenceV2:
    run_identity_sha256: str
    run_document_sha256: str
    report_sha256: str
    _run_bytes: bytes = field(repr=False)
    _report_bytes: bytes = field(repr=False)

    @property
    def run_bytes(self):
        return self._run_bytes

    @property
    def report_bytes(self):
        return self._report_bytes


def spine42_v3_export_evidence_profile_v2() -> dict[str, Any]:
    return json.loads(_canonical(_EVIDENCE_PROFILE))


def build_spine42_v3_export_evidence_v2(
    project_id: str, clip_id: str, p3: Mapping[str, str],
    motion_instance_v3: Mapping[str, str], outputs: Mapping[str, str],
    validated: ValidatedSpine42Export,
) -> Spine42V3ExportEvidenceV2:
    """Build v2-only run/report bytes with no current-head claim."""

    try:
        source_contract = spine42_source_contract_v3_v2()
        source_contract_sha = spine42_source_contract_v3_v2_sha256()
        inputs = {
            "p3": dict(p3),
            "motion_instance_v3_v2": dict(motion_instance_v3),
            "source_images": [
                {"attachment_id": name, "sha256": sha}
                for name, sha in validated.source_images
            ],
        }
        run_base = {
            "format": "autospine-spine42-v3-export-run",
            "format_version": 2, "project_id": project_id,
            "clip_id": clip_id,
            "source_contract": source_contract,
            "source_contract_sha256": source_contract_sha,
            "adapter_profile": spine42_target_profile_v3_v2(),
            "adapter_profile_sha256":
                spine42_target_profile_v3_v2_sha256(),
            "evidence_profile": spine42_v3_export_evidence_profile_v2(),
            "inputs": inputs, "outputs": dict(outputs),
            "authority": _authority(), "release_gate": _gate(),
        }
        identity = _domain_hash(RUN_IDENTITY_DOMAIN, _canonical(run_base))
        run_bytes = _bounded_json(
            {**run_base, "run_identity_sha256": identity},
            MAX_RUN_MANIFEST_BYTES, "run manifest",
        )
        run_sha = _sha(run_bytes)
        report = {
            "format": "autospine-spine42-v3-export-report",
            "format_version": 2, "status": "passed",
            "project_id": project_id, "clip_id": clip_id,
            "source": {
                "p3": dict(p3),
                "motion_instance_v3_v2": dict(motion_instance_v3),
                "source_contract_sha256": source_contract_sha,
                "adapter_profile_sha256":
                    spine42_target_profile_v3_v2_sha256(),
                "run_identity_sha256": identity,
                "run_document_sha256": run_sha,
            },
            "outputs": dict(outputs),
            "checks": [
                {"id": name, "status": "passed"} for name in (
                    "adapter-profile", "source-contract-v2",
                    "motion-instance-v3-v2-binding",
                    "attachment-atlas-binding", "atlas-png-geometry",
                    "source-image-binding",
                )
            ],
            "metrics": {
                "bones": validated.bone_count,
                "slots": validated.slot_count,
                "attachments": validated.attachment_count,
                "animations": validated.animation_count,
                "events": validated.event_count,
                "atlas_regions": len(validated.attachment_paths),
                "atlas_width": validated.atlas_width,
                "atlas_height": validated.atlas_height,
                "source_images": len(validated.source_images),
            },
            "authority": _authority(), "release_gate": _gate(),
        }
        report_bytes = _bounded_json(
            report, MAX_EXPORT_REPORT_BYTES, "export report",
        )
        return Spine42V3ExportEvidenceV2(
            identity, run_sha, _sha(report_bytes), run_bytes, report_bytes,
        )
    except Spine42V3ExportEvidenceV2Error:
        raise
    except (AttributeError, OverflowError, TypeError, ValueError) as exc:
        raise Spine42V3ExportEvidenceV2Error(
            f"Spine 4.2 v2-source evidence failed: {exc}"
        ) from exc


def _bounded_json(value, limit, label):
    data = _canonical(value)
    if len(data) > limit:
        raise Spine42V3ExportEvidenceV2Error(
            f"P10.7a v2 {label} exceeds its byte limit"
        )
    return data


def _canonical(value):
    try:
        return json.dumps(
            value, ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
    except (OverflowError, TypeError, ValueError) as exc:
        raise Spine42V3ExportEvidenceV2Error(
            "P10.7a v2 evidence is not finite JSON"
        ) from exc


def _authority():
    return dict(AUTHORITY)


def _gate():
    return {"status": "blocked", "reason_codes": list(_REASONS)}


def _domain_hash(domain, payload):
    digest = hashlib.sha256()
    for value in (domain, payload):
        digest.update(len(value).to_bytes(8, "big"))
        digest.update(value)
    return digest.hexdigest()


def _sha(value):
    return hashlib.sha256(value).hexdigest()


__all__ = [
    "AUTHORITY", "BUNDLE_INVENTORY", "MAX_EXPORT_REPORT_BYTES",
    "MAX_RUN_MANIFEST_BYTES", "RELEASE_GATE", "RUN_IDENTITY_DOMAIN",
    "Spine42V3ExportEvidenceV2", "Spine42V3ExportEvidenceV2Error",
    "build_spine42_v3_export_evidence_v2",
    "spine42_v3_export_evidence_profile_v2",
]
