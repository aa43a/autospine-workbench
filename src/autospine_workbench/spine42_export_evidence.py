"""Canonical run and semantic report evidence for Spine 4.2 exports."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any

from .spine42_contract import spine42_target_profile
from .spine42_export_validation import ValidatedSpine42Export


MAX_RUN_MANIFEST_BYTES = 2 * 1024 * 1024
MAX_EXPORT_REPORT_BYTES = 2 * 1024 * 1024
RUN_IDENTITY_DOMAIN = b"autospine-spine42-export-run-identity/v1"


class Spine42ExportEvidenceError(ValueError):
    """Raised when canonical export evidence cannot be represented."""


@dataclass(frozen=True, slots=True)
class Spine42ExportEvidence:
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


def build_spine42_export_evidence(
    project: str,
    mode: str,
    p3: dict[str, str],
    p5: dict[str, str] | None,
    outputs: dict[str, str],
    validated: ValidatedSpine42Export,
) -> Spine42ExportEvidence:
    """Build the exact run identity, manifest bytes, and passed report."""

    inputs: dict[str, Any] = {
        "p3": p3,
        "p5": p5,
        "source_images": [
            {"path": path, "sha256": sha}
            for path, sha in validated.source_images
        ],
    }
    run_base = {
        "format": "autospine-spine42-export-run",
        "format_version": 1,
        "project_id": project,
        "mode": mode,
        "adapter_profile": spine42_target_profile(),
        "inputs": inputs,
        "outputs": outputs,
    }
    identity = _domain_hash(RUN_IDENTITY_DOMAIN, _canonical(run_base))
    run_bytes = _bounded_json(
        {**run_base, "run_identity_sha256": identity},
        MAX_RUN_MANIFEST_BYTES,
        "run manifest",
    )
    run_sha = _sha(run_bytes)
    report = {
        "format": "autospine-spine42-export-report",
        "format_version": 1,
        "status": "passed",
        "project_id": project,
        "mode": mode,
        "source": {
            "p3": p3,
            "p5": p5,
            "run_identity_sha256": identity,
            "run_document_sha256": run_sha,
        },
        "outputs": outputs,
        "checks": [
            {"id": "adapter-profile", "status": "passed"},
            {"id": "attachment-atlas-binding", "status": "passed"},
            {"id": "atlas-png-geometry", "status": "passed"},
            {"id": "source-image-binding", "status": "passed"},
            {"id": "motion-binding", "status": (
                "not_applicable" if p5 is None else "passed"
            )},
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
    }
    report_bytes = _bounded_json(
        report, MAX_EXPORT_REPORT_BYTES, "export report"
    )
    return Spine42ExportEvidence(
        identity, run_sha, _sha(report_bytes), run_bytes, report_bytes
    )


def _bounded_json(value: Any, limit: int, label: str) -> bytes:
    data = _canonical(value)
    if len(data) > limit:
        raise Spine42ExportEvidenceError(f"{label} exceeds its byte limit")
    return data


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(
            value, ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
    except (OverflowError, TypeError, ValueError) as exc:
        raise Spine42ExportEvidenceError("Export evidence is not finite JSON") from exc


def _domain_hash(domain: bytes, payload: bytes) -> str:
    digest = hashlib.sha256()
    for value in (domain, payload):
        digest.update(len(value).to_bytes(8, "big"))
        digest.update(value)
    return digest.hexdigest()


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()
