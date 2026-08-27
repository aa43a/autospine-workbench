"""Canonical unreviewed evidence for official Spine 4.2 v3 captures."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import hashlib
import json
from typing import Any

from .browser_executable_snapshot import BrowserExecutableSnapshot
from .browser_version_identity import browser_version_identity_sha256
from .spine42_runtime_inputs import Spine42RuntimePackage
from .spine42_v3_bundle_integrity import VerifiedSpine42V3Bundle
from .spine42_v3_raster_metrics import (
    canonical_spine42_v3_raster_metrics_bytes,
    compute_spine42_v3_raster_metrics,
    spine42_v3_raster_metrics_sha256,
)
from .spine42_v3_runtime_plan import (
    build_spine42_v3_runtime_plan,
    canonical_spine42_v3_runtime_plan_bytes,
    spine42_v3_runtime_plan_sha256,
)
from .spine42_v3_runtime_session import build_spine42_v3_runtime_sessions


MANIFEST_NAME, METRICS_NAME = "capture-manifest.json", "metrics.json"
FORMAT, FORMAT_VERSION = "autospine-spine42-v3-runtime-capture", 1
MAX_MANIFEST_BYTES = MAX_METRICS_BYTES = 16 * 1024 * 1024
MAX_CAPTURE_BYTES = 8 * 1024 * 1024
MAX_CAPTURE_TOTAL_BYTES = 512 * 1024 * 1024
AUTHORITY = {
    "official_runtime_loaded": True,
    "isolated_attachment_raster_captured": True,
    "raster_metrics_computed": True,
    "human_visual_reviewed": False,
    "raster_visual_quality_approved": False,
    "continuous_time_safety_claimed": False,
    "publish_authority": False,
    "release_authority": False,
}
RELEASE_GATE = {
    "status": "blocked",
    "reason_codes": [
        "human_visual_review_missing", "raster_visual_quality_unapproved",
        "continuous_time_safety_unproven", "publish_authority_not_granted",
        "release_authority_not_granted",
    ],
}


class Spine42V3RuntimeEvidenceError(ValueError):
    """Raised when capture bytes cannot prove the bounded runtime run."""
@dataclass(frozen=True, slots=True)
class Spine42V3RuntimeEvidence:
    project_id: str
    clip_id: str
    spine42_v3_bundle_sha256: str
    skeleton_json_sha256: str
    run_document_sha256: str
    capture_plan_sha256: str
    raster_metrics_sha256: str
    _manifest_bytes: bytes = field(repr=False)
    _metrics_bytes: bytes = field(repr=False)
    _capture_items: tuple[tuple[str, bytes], ...] = field(repr=False)

    @property
    def manifest_bytes(self) -> bytes:
        return self._manifest_bytes
    @property
    def metrics_bytes(self) -> bytes:
        return self._metrics_bytes
    @property
    def capture_bytes(self) -> dict[str, bytes]:
        return dict(self._capture_items)
    @property
    def manifest(self) -> dict[str, Any]:
        return json.loads(self._manifest_bytes)
    @property
    def metrics(self) -> dict[str, Any]:
        return json.loads(self._metrics_bytes)
def build_spine42_v3_runtime_evidence(
    bundle: VerifiedSpine42V3Bundle,
    runtime: Spine42RuntimePackage,
    browser: BrowserExecutableSnapshot,
    plan: Mapping[str, Any],
    collector_snapshot: Any,
    raster_metrics: Mapping[str, Any],
    *, license_acknowledged: bool,
) -> Spine42V3RuntimeEvidence:
    """Compile exact official-runtime inputs without visual approval."""

    try:
        if type(bundle) is not VerifiedSpine42V3Bundle \
                or type(runtime) is not Spine42RuntimePackage \
                or type(browser) is not BrowserExecutableSnapshot \
                or license_acknowledged is not True:
            raise Spine42V3RuntimeEvidenceError(
                "Exact inputs and license acknowledgement are required"
            )
        expected_plan = build_spine42_v3_runtime_plan(bundle)
        if canonical_spine42_v3_runtime_plan_bytes(plan) != \
                canonical_spine42_v3_runtime_plan_bytes(expected_plan):
            raise Spine42V3RuntimeEvidenceError(
                "Capture plan differs from exact Spine v3 bundle replay"
            )
        sessions = build_spine42_v3_runtime_sessions(
            bundle, runtime, expected_plan
        )
        require_digest(runtime.package_json_sha256, "runtime package.json")
        require_digest(runtime.license_sha256, "runtime license")
        captures = _snapshot_captures(collector_snapshot, expected_plan)
        expected_metrics = compute_spine42_v3_raster_metrics(
            expected_plan, captures
        )
        if canonical_spine42_v3_raster_metrics_bytes(raster_metrics) != \
                canonical_spine42_v3_raster_metrics_bytes(expected_metrics):
            raise Spine42V3RuntimeEvidenceError(
                "Raster metrics differ from exact PNG-byte replay"
            )
        reports = _snapshot_reports(
            collector_snapshot, sessions.plan, sessions.sha256, captures
        )
        metrics_bytes = canonical_json_bytes(
            expected_metrics, MAX_METRICS_BYTES, "raster metrics"
        )
        source = {
            "skeleton_json_sha256": bundle.skeleton_json_sha256,
            "spine42_v3_bundle_sha256": bundle.bundle_sha256,
            "run_document_sha256": bundle.run_document_sha256,
            "capture_plan_sha256":
                spine42_v3_runtime_plan_sha256(expected_plan),
            "runtime_session_set_sha256": sessions.sha256,
            "raster_metrics_sha256":
                spine42_v3_raster_metrics_sha256(expected_metrics),
        }
        document = {
            "format": FORMAT, "format_version": FORMAT_VERSION,
            "project_id": bundle.project_id, "clip_id": bundle.clip_id,
            "source": source,
            "runtime": {
                **expected_plan["runtime"],
                "package_json_sha256": runtime.package_json_sha256,
                "license_sha256": runtime.license_sha256,
                "license_acknowledged": True,
                "license_file_presence_is_authorization": False,
            },
            "browser": browser_document(browser),
            "plan": expected_plan, "reports": reports,
            "artifacts": artifact_inventory(expected_plan, captures),
            "authority": json_copy(AUTHORITY),
            "status": "captured_unreviewed",
            "release_gate": json_copy(RELEASE_GATE),
        }
        return replay_spine42_v3_runtime_evidence(
            canonical_json_bytes(document, MAX_MANIFEST_BYTES, "manifest"),
            metrics_bytes, tuple(captures.items()),
        )
    except Spine42V3RuntimeEvidenceError:
        raise
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise Spine42V3RuntimeEvidenceError(
            f"Spine v3 runtime evidence compilation failed: {exc}"
        ) from exc


def replay_spine42_v3_runtime_evidence(
    manifest_bytes: bytes, metrics_bytes: bytes,
    capture_items: tuple[tuple[str, bytes], ...],
) -> Spine42V3RuntimeEvidence:
    """Replay exact stored structures and bytes without mutable heads."""
    from .spine42_v3_runtime_bundle import replay_runtime_evidence
    return replay_runtime_evidence(manifest_bytes, metrics_bytes, capture_items)


def _snapshot_captures(snapshot, plan) -> dict[str, bytes]:
    captures = getattr(snapshot, "capture_bytes", None)
    ids = [row["artifact_id"] for row in plan["artifacts"]]
    if type(captures) is not dict or set(captures) != set(ids):
        raise Spine42V3RuntimeEvidenceError(
            "Collector PNG inventory differs from the capture plan"
        )
    return {identifier: captures[identifier] for identifier in ids}
def _snapshot_reports(snapshot, plan, session_sha, captures):
    reports = getattr(snapshot, "reports", None)
    if type(reports) is not tuple:
        raise Spine42V3RuntimeEvidenceError("Collector report type is invalid")
    result = [json_copy(row) for row in reports]
    validate_reports(result, plan, session_sha, captures)
    return result


def validate_reports(reports, plan, session_sha, captures) -> None:
    """Bind ordered collector callbacks to sessions and PNG bytes."""

    artifacts = plan["artifacts"]
    cases = {row["case_id"]: row for row in plan["cases"]}
    if type(reports) is not list or len(reports) != len(artifacts):
        raise Spine42V3RuntimeEvidenceError("Capture report count is invalid")
    for report, artifact in zip(reports, artifacts, strict=True):
        image = report.get("image") if type(report) is dict else None
        observed = report.get("observables") if type(report) is dict else None
        raw = captures[artifact["artifact_id"]]
        report_fields = {
            "status", "session_set_sha256", "plan_sha256", "source",
            "runtime", "assets", "capture", "case", "artifact",
            "observables", "image",
        }
        image_fields = {"path", "png_sha256", "width", "height", "size_bytes"}
        observed_fields = {
            "official_runtime_loaded", "clip_ids", "slot_ids",
            "attachments", "isolation",
        }
        viewport = plan["capture"]["viewport"]
        dpr = plan["capture"]["device_pixel_ratio"]
        if set(report) != report_fields or report.get("status") != "captured" \
                or report.get("session_set_sha256") != session_sha \
                or report.get("plan_sha256") != plan["capture_plan_sha256"] \
                or report.get("source") != plan["source"] \
                or report.get("runtime") != plan["runtime"] \
                or report.get("capture") != plan["capture"] \
                or report.get("case") != cases[artifact["case_id"]] \
                or report.get("artifact") != artifact \
                or type(observed) is not dict \
                or set(observed) != observed_fields \
                or observed.get("official_runtime_loaded") is not True \
                or type(image) is not dict \
                or set(image) != image_fields \
                or image.get("path") != artifact["path"] \
                or image.get("png_sha256") != sha256(raw) \
                or image.get("size_bytes") != len(raw) \
                or image.get("width") != viewport["width"] * dpr \
                or image.get("height") != viewport["height"] * dpr:
            raise Spine42V3RuntimeEvidenceError(
                "Capture report differs from its exact session or PNG"
            )


def artifact_inventory(plan, captures) -> list[dict[str, Any]]:
    """Describe the sole logical-id to stored-path mapping."""
    return [{
        "artifact_id": row["artifact_id"], "logical_path": row["path"],
        "stored_path": f"captures/{row['path']}", "kind": row["kind"],
        "case_id": row["case_id"], "sha256": sha256(captures[row["artifact_id"]]),
        "size_bytes": len(captures[row["artifact_id"]]),
    } for row in plan["artifacts"]]


def browser_document(value: BrowserExecutableSnapshot) -> dict[str, Any]:
    """Return the content identity, intentionally excluding local path."""
    result = {
        "family": value.family, "reported_version": value.reported_version,
        "version_output_sha256": value.version_output_sha256,
        "executable_sha256": value.executable_sha256,
        "size_bytes": value.size_bytes,
    }
    if result["version_output_sha256"] != browser_version_identity_sha256(
        result["family"], result["reported_version"]
    ) or type(result["size_bytes"]) is not int or result["size_bytes"] <= 0:
        raise Spine42V3RuntimeEvidenceError("Browser identity is invalid")
    require_digest(result["executable_sha256"], "browser executable")
    return result
def canonical_json_bytes(value, limit, label) -> bytes:
    try:
        raw = json.dumps(
            value, ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
    except (OverflowError, TypeError, UnicodeError, ValueError) as exc:
        raise Spine42V3RuntimeEvidenceError(f"{label} is not finite JSON") from exc
    if not 0 < len(raw) <= limit:
        raise Spine42V3RuntimeEvidenceError(f"{label} exceeds its byte limit")
    return raw
def json_copy(value):
    return json.loads(canonical_json_bytes(
        value, MAX_MANIFEST_BYTES, "evidence value"
    ))
def require_digest(value, label) -> None:
    if type(value) is not str or len(value) != 64 \
            or any(character not in "0123456789abcdef" for character in value):
        raise Spine42V3RuntimeEvidenceError(f"{label} digest is invalid")
def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


__all__ = [
    "AUTHORITY", "FORMAT", "FORMAT_VERSION", "MANIFEST_NAME",
    "MAX_CAPTURE_BYTES", "MAX_CAPTURE_TOTAL_BYTES", "MAX_MANIFEST_BYTES",
    "MAX_METRICS_BYTES", "METRICS_NAME", "RELEASE_GATE",
    "Spine42V3RuntimeEvidence", "Spine42V3RuntimeEvidenceError",
    "build_spine42_v3_runtime_evidence",
    "replay_spine42_v3_runtime_evidence",
]
