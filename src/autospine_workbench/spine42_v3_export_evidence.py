"""Canonical provenance and bounded evidence for Spine 4.2 v3 exports."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import hashlib
import json
from types import MappingProxyType
from typing import Any

from .spine42_contract_v3 import (
    spine42_target_profile_v3,
    spine42_target_profile_v3_sha256,
)
from .spine42_export_validation import ValidatedSpine42Export


MAX_RUN_MANIFEST_BYTES = 2 * 1024 * 1024
MAX_EXPORT_REPORT_BYTES = 2 * 1024 * 1024
RUN_IDENTITY_DOMAIN = b"autospine-spine42-v3-export-run-identity/v1"
BUNDLE_INVENTORY = (
    "skeleton.json", "skeleton.atlas", "skeleton.png",
    "run-manifest.json", "export-report.json",
)
_EVIDENCE_PROFILE = {
    "id": "autospine-spine42-v3-export-evidence",
    "version": "1.0.0",
    "canonicalization": "canonical-json-utf8-sort-keys-no-nonfinite",
    "bundle_inventory": list(BUNDLE_INVENTORY),
}
AUTHORITY = MappingProxyType({
    "spine_adapter_emitted": True,
    "official_runtime_loaded": False,
    "raster_visual_quality": False,
    "persistent_current_head_authority": False,
    "publishable_spine_timeline": False,
    "release_authority": False,
})
RELEASE_GATE = MappingProxyType({
    "status": "blocked",
    "reason_codes": (
        "complete_attachment_boundary_not_proven",
        "official_runtime_not_loaded",
        "persistent_current_head_authority_not_granted",
        "publishable_spine_timeline_not_granted",
        "raster_visual_quality_unproven",
    ),
})


class Spine42V3ExportEvidenceError(ValueError):
    """Raised when canonical v3 export evidence cannot be represented."""


@dataclass(frozen=True, slots=True)
class Spine42V3ExportEvidence:
    run_identity_sha256: str
    run_document_sha256: str
    report_sha256: str
    _run_bytes: bytes = field(repr=False)
    _report_bytes: bytes = field(repr=False)

    @property
    def run_bytes(self) -> bytes:
        return self._run_bytes

    @property
    def report_bytes(self) -> bytes:
        return self._report_bytes


def spine42_v3_export_evidence_profile() -> dict[str, Any]:
    """Return a detached copy of the pinned export-evidence profile."""

    return json.loads(_canonical(_EVIDENCE_PROFILE))


def build_spine42_v3_export_evidence(
    project_id: str,
    clip_id: str,
    p3: Mapping[str, str],
    motion_instance_v3: Mapping[str, str],
    outputs: Mapping[str, str],
    validated: ValidatedSpine42Export,
) -> Spine42V3ExportEvidence:
    """Build exact run identity, run bytes, and a structural report."""

    try:
        inputs = {
            "p3": dict(p3),
            "motion_instance_v3": dict(motion_instance_v3),
            "source_images": [
                {"path": path, "sha256": sha}
                for path, sha in validated.source_images
            ],
        }
        run_base = {
            "format": "autospine-spine42-v3-export-run",
            "format_version": 1,
            "project_id": project_id,
            "clip_id": clip_id,
            "adapter_profile": spine42_target_profile_v3(),
            "adapter_profile_sha256": spine42_target_profile_v3_sha256(),
            "evidence_profile": spine42_v3_export_evidence_profile(),
            "inputs": inputs,
            "outputs": dict(outputs),
            "authority": _fixed_authority(),
            "release_gate": _fixed_release_gate(),
        }
        identity = _domain_hash(RUN_IDENTITY_DOMAIN, _canonical(run_base))
        run_bytes = _bounded_json(
            {**run_base, "run_identity_sha256": identity},
            MAX_RUN_MANIFEST_BYTES,
            "run manifest",
        )
        run_sha = _sha(run_bytes)
        report = {
            "format": "autospine-spine42-v3-export-report",
            "format_version": 1,
            "status": "passed",
            "project_id": project_id,
            "clip_id": clip_id,
            "source": {
                "p3": dict(p3),
                "motion_instance_v3": dict(motion_instance_v3),
                "adapter_profile_sha256": spine42_target_profile_v3_sha256(),
                "run_identity_sha256": identity,
                "run_document_sha256": run_sha,
            },
            "outputs": dict(outputs),
            "checks": [
                {"id": "adapter-profile", "status": "passed"},
                {"id": "motion-instance-v3-binding", "status": "passed"},
                {"id": "attachment-atlas-binding", "status": "passed"},
                {"id": "atlas-png-geometry", "status": "passed"},
                {"id": "source-image-binding", "status": "passed"},
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
            "authority": _fixed_authority(),
            "release_gate": _fixed_release_gate(),
        }
        report_bytes = _bounded_json(
            report, MAX_EXPORT_REPORT_BYTES, "export report"
        )
        return Spine42V3ExportEvidence(
            identity, run_sha, _sha(report_bytes), run_bytes, report_bytes
        )
    except Spine42V3ExportEvidenceError:
        raise
    except (AttributeError, OverflowError, TypeError, ValueError) as exc:
        raise Spine42V3ExportEvidenceError(
            f"Spine 4.2 v3 export evidence failed: {exc}"
        ) from exc


def _bounded_json(value: Any, limit: int, label: str) -> bytes:
    data = _canonical(value)
    if len(data) > limit:
        raise Spine42V3ExportEvidenceError(f"{label} exceeds its byte limit")
    return data


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(
            value, ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
    except (OverflowError, TypeError, ValueError) as exc:
        raise Spine42V3ExportEvidenceError(
            "Export evidence is not finite JSON"
        ) from exc


def _fixed_authority() -> dict[str, bool]:
    """Return a fresh authority document that cannot inherit mutation."""

    return {
        "spine_adapter_emitted": True,
        "official_runtime_loaded": False,
        "raster_visual_quality": False,
        "persistent_current_head_authority": False,
        "publishable_spine_timeline": False,
        "release_authority": False,
    }


def _fixed_release_gate() -> dict[str, Any]:
    """Return the exact blocked gate as a fresh JSON value."""

    return {
        "status": "blocked",
        "reason_codes": [
            "complete_attachment_boundary_not_proven",
            "official_runtime_not_loaded",
            "persistent_current_head_authority_not_granted",
            "publishable_spine_timeline_not_granted",
            "raster_visual_quality_unproven",
        ],
    }


def _domain_hash(domain: bytes, payload: bytes) -> str:
    digest = hashlib.sha256()
    for value in (domain, payload):
        digest.update(len(value).to_bytes(8, "big"))
        digest.update(value)
    return digest.hexdigest()


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


__all__ = [
    "AUTHORITY", "BUNDLE_INVENTORY", "MAX_EXPORT_REPORT_BYTES",
    "MAX_RUN_MANIFEST_BYTES", "RELEASE_GATE", "RUN_IDENTITY_DOMAIN",
    "Spine42V3ExportEvidence", "Spine42V3ExportEvidenceError",
    "build_spine42_v3_export_evidence",
    "spine42_v3_export_evidence_profile",
]
