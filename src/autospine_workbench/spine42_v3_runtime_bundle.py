"""Immutable byte bundle and exact replay for P10.7b runtime evidence."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
from typing import Any

from .browser_version_identity import browser_version_identity_sha256
from .spine42_v3_raster_metrics import (
    canonical_spine42_v3_raster_metrics_bytes,
    compute_spine42_v3_raster_metrics,
    spine42_v3_raster_metrics_sha256,
)
from .spine42_v3_runtime_evidence import (
    AUTHORITY, FORMAT, FORMAT_VERSION, MANIFEST_NAME,
    MAX_CAPTURE_BYTES, MAX_CAPTURE_TOTAL_BYTES, MAX_MANIFEST_BYTES,
    MAX_METRICS_BYTES, METRICS_NAME, RELEASE_GATE,
    Spine42V3RuntimeEvidence, Spine42V3RuntimeEvidenceError,
    canonical_json_bytes, require_digest, sha256, validate_reports,
)
from .spine42_v3_runtime_plan import spine42_v3_runtime_plan_sha256
from .spine42_v3_runtime_profile import MAX_CAPTURE_ARTIFACTS


NAMESPACE = "spine42-v3-runtime"
BUNDLE_ADDRESS_DOMAIN = b"autospine.spine42-v3-runtime-bundle/v1\x00"


class Spine42V3RuntimeBundleError(ValueError):
    """Raised when runtime evidence cannot form its fixed disk bundle."""
@dataclass(frozen=True, slots=True)
class Spine42V3RuntimeBundle:
    project_id: str
    clip_id: str
    spine42_v3_bundle_sha256: str
    skeleton_json_sha256: str
    run_document_sha256: str
    manifest_sha256: str
    metrics_sha256: str
    bundle_sha256: str
    _file_items: tuple[tuple[str, bytes], ...] = field(repr=False)

    @property
    def file_items(self) -> tuple[tuple[str, bytes], ...]:
        return self._file_items
def build_spine42_v3_runtime_bundle(
    evidence: Spine42V3RuntimeEvidence,
) -> Spine42V3RuntimeBundle:
    """Replay evidence and length-frame every fixed path and payload."""
    try:
        if type(evidence) is not Spine42V3RuntimeEvidence:
            raise Spine42V3RuntimeBundleError(
                "Runtime bundle requires exact evidence"
            )
        replayed = replay_runtime_evidence(
            evidence.manifest_bytes, evidence.metrics_bytes,
            tuple(evidence.capture_bytes.items()),
        )
        if replayed != evidence:
            raise Spine42V3RuntimeBundleError(
                "Runtime evidence differs from exact replay"
            )
        manifest = evidence.manifest
        captures = evidence.capture_bytes
        files = (
            (MANIFEST_NAME, evidence.manifest_bytes),
            (METRICS_NAME, evidence.metrics_bytes),
        ) + tuple(
            (row["stored_path"], captures[row["artifact_id"]])
            for row in manifest["artifacts"]
        )
        address = spine42_v3_runtime_bundle_sha256(files)
        return Spine42V3RuntimeBundle(
            evidence.project_id, evidence.clip_id,
            evidence.spine42_v3_bundle_sha256,
            evidence.skeleton_json_sha256, evidence.run_document_sha256,
            sha256(evidence.manifest_bytes), sha256(evidence.metrics_bytes),
            address, files,
        )
    except (Spine42V3RuntimeEvidenceError, KeyError, TypeError) as exc:
        raise Spine42V3RuntimeBundleError(
            f"Runtime evidence bundle compilation failed: {exc}"
        ) from exc


def replay_runtime_evidence(
    manifest_bytes: bytes, metrics_bytes: bytes,
    capture_items: tuple[tuple[str, bytes], ...],
) -> Spine42V3RuntimeEvidence:
    """Recompute plan, reports, artifacts, metrics, and source seals."""
    try:
        manifest = _document(
            manifest_bytes, MAX_MANIFEST_BYTES, "capture manifest"
        )
        metrics = _document(metrics_bytes, MAX_METRICS_BYTES, "metrics")
        _fixed_manifest(manifest)
        plan, source = manifest["plan"], manifest["source"]
        plan_sha = spine42_v3_runtime_plan_sha256(plan)
        captures = _capture_items(
            capture_items, manifest["artifacts"], plan["artifacts"]
        )
        recomputed = compute_spine42_v3_raster_metrics(plan, captures)
        if canonical_spine42_v3_raster_metrics_bytes(recomputed) != metrics_bytes:
            raise Spine42V3RuntimeEvidenceError(
                "Stored metrics differ from exact capture replay"
            )
        metrics_sha = spine42_v3_raster_metrics_sha256(metrics)
        expected_plan_source = {
            "project_id": manifest["project_id"],
            "clip_id": manifest["clip_id"],
            "skeleton_json_sha256": source["skeleton_json_sha256"],
            "bundle_sha256": source["spine42_v3_bundle_sha256"],
        }
        if plan["source"] != expected_plan_source \
                or source["capture_plan_sha256"] != plan_sha \
                or source["raster_metrics_sha256"] != metrics_sha:
            raise Spine42V3RuntimeEvidenceError(
                "Runtime evidence source identities are cross-wired"
            )
        validate_reports(
            manifest["reports"], plan,
            source["runtime_session_set_sha256"], captures,
        )
        return Spine42V3RuntimeEvidence(
            manifest["project_id"], manifest["clip_id"],
            source["spine42_v3_bundle_sha256"],
            source["skeleton_json_sha256"], source["run_document_sha256"],
            plan_sha, metrics_sha, manifest_bytes, metrics_bytes,
            tuple(captures.items()),
        )
    except Spine42V3RuntimeEvidenceError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise Spine42V3RuntimeEvidenceError(
            f"Runtime evidence replay failed: {exc}"
        ) from exc


def spine42_v3_runtime_bundle_sha256(
    file_items: tuple[tuple[str, bytes], ...],
) -> str:
    """Hash the domain, item count, every filename, length, and payload."""
    items = tuple(file_items)
    if not 3 <= len(items) <= MAX_CAPTURE_ARTIFACTS + 2 \
            or tuple(row[0] for row in items[:2]) != (
                MANIFEST_NAME, METRICS_NAME
            ):
        raise Spine42V3RuntimeBundleError("Runtime bundle inventory is invalid")
    digest, folded, total = hashlib.sha256(), set(), 0
    _frame(digest, BUNDLE_ADDRESS_DOMAIN)
    _frame(digest, len(items).to_bytes(8, "big"))
    for index, item in enumerate(items):
        if type(item) is not tuple or len(item) != 2:
            raise Spine42V3RuntimeBundleError("Runtime bundle item is invalid")
        path, payload = item
        limit = (
            MAX_MANIFEST_BYTES if index == 0 else
            MAX_METRICS_BYTES if index == 1 else MAX_CAPTURE_BYTES
        )
        valid_capture = index < 2 or _safe_capture_path(path)
        if type(path) is not str or path.casefold() in folded \
                or not valid_capture or type(payload) is not bytes \
                or not 0 < len(payload) <= limit:
            raise Spine42V3RuntimeBundleError(
                "Runtime bundle path or payload is invalid"
            )
        folded.add(path.casefold())
        if index >= 2:
            total += len(payload)
        _frame(digest, path.encode("utf-8"))
        _frame(digest, payload)
    if total > MAX_CAPTURE_TOTAL_BYTES:
        raise Spine42V3RuntimeBundleError("Runtime PNG total is too large")
    return digest.hexdigest()
def _fixed_manifest(value) -> None:
    fields = {
        "format", "format_version", "project_id", "clip_id", "source",
        "runtime", "browser", "plan", "reports", "artifacts", "authority",
        "status", "release_gate",
    }
    source_fields = {
        "skeleton_json_sha256", "spine42_v3_bundle_sha256",
        "run_document_sha256", "capture_plan_sha256",
        "runtime_session_set_sha256", "raster_metrics_sha256",
    }
    source = value.get("source", {})
    if set(value) != fields or value.get("format") != FORMAT \
            or value.get("format_version") != FORMAT_VERSION \
            or set(source) != source_fields \
            or value.get("runtime", {}).get("license_acknowledged") is not True \
            or value.get("authority") != AUTHORITY \
            or value.get("status") != "captured_unreviewed" \
            or value.get("release_gate") != RELEASE_GATE:
        raise Spine42V3RuntimeEvidenceError(
            "Runtime manifest structure or authority is invalid"
        )
    runtime = value.get("runtime", {})
    expected_runtime = {
        **value["plan"]["runtime"],
        "package_json_sha256": runtime.get("package_json_sha256"),
        "license_sha256": runtime.get("license_sha256"),
        "license_acknowledged": True,
        "license_file_presence_is_authorization": False,
    }
    if runtime != expected_runtime \
            or not any(row.get("kind") == "attachment_isolate"
                 for row in value.get("artifacts", [])):
        raise Spine42V3RuntimeEvidenceError(
            "Runtime or isolated raster evidence is incomplete"
        )
    for name in source_fields:
        require_digest(source[name], name)
    require_digest(runtime["package_json_sha256"], "runtime package.json")
    require_digest(runtime["license_sha256"], "runtime license")
    _browser(value.get("browser"))


def _capture_items(items, artifacts, planned) -> dict[str, bytes]:
    if type(items) is not tuple or type(artifacts) is not list \
            or len(items) != len(artifacts) or len(artifacts) != len(planned):
        raise Spine42V3RuntimeEvidenceError("Capture inventory is invalid")
    result, total = {}, 0
    for item, row, plan_row in zip(items, artifacts, planned, strict=True):
        identifier, raw = item if type(item) is tuple and len(item) == 2 else (None, None)
        logical = row.get("logical_path")
        expected_fields = {
            "artifact_id", "logical_path", "stored_path", "kind", "case_id",
            "sha256", "size_bytes",
        }
        if type(row) is not dict or set(row) != expected_fields \
                or identifier != row.get("artifact_id") \
                or row.get("stored_path") != f"captures/{logical}" \
                or (row.get("artifact_id"), logical, row.get("kind"),
                    row.get("case_id")) != (
                    plan_row.get("artifact_id"), plan_row.get("path"),
                    plan_row.get("kind"), plan_row.get("case_id"),
                ) \
                or not _safe_basename(logical) or identifier in result \
                or type(raw) is not bytes or not 0 < len(raw) <= MAX_CAPTURE_BYTES \
                or row.get("sha256") != sha256(raw) \
                or row.get("size_bytes") != len(raw):
            raise Spine42V3RuntimeEvidenceError("Capture artifact is invalid")
        result[identifier], total = raw, total + len(raw)
    if total > MAX_CAPTURE_TOTAL_BYTES:
        raise Spine42V3RuntimeEvidenceError("Capture total exceeds its limit")
    return result


def _browser(value) -> None:
    fields = {
        "family", "reported_version", "version_output_sha256",
        "executable_sha256", "size_bytes",
    }
    if type(value) is not dict or set(value) != fields \
            or value["version_output_sha256"] != browser_version_identity_sha256(
                value["family"], value["reported_version"]
            ) or type(value["size_bytes"]) is not int or value["size_bytes"] <= 0:
        raise Spine42V3RuntimeEvidenceError("Browser identity is invalid")
    require_digest(value["executable_sha256"], "browser executable")


def _document(raw, limit, label):
    if type(raw) is not bytes or not 0 < len(raw) <= limit:
        raise Spine42V3RuntimeEvidenceError(f"{label} bytes are unbounded")
    try:
        value = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise Spine42V3RuntimeEvidenceError(f"{label} is not JSON") from exc
    if type(value) is not dict \
            or canonical_json_bytes(value, limit, label) != raw:
        raise Spine42V3RuntimeEvidenceError(f"{label} is not canonical JSON")
    return value


def _safe_basename(value) -> bool:
    return type(value) is str and Path(value).name == value \
        and value.endswith(".png") and "\\" not in value and "\x00" not in value


def _safe_capture_path(value) -> bool:
    return type(value) is str and value.startswith("captures/") \
        and value.count("/") == 1 and _safe_basename(value[9:])


def _frame(digest: Any, value: bytes) -> None:
    digest.update(len(value).to_bytes(8, "big"))
    digest.update(value)


__all__ = [
    "BUNDLE_ADDRESS_DOMAIN", "NAMESPACE", "Spine42V3RuntimeBundle",
    "Spine42V3RuntimeBundleError", "build_spine42_v3_runtime_bundle",
    "replay_runtime_evidence", "spine42_v3_runtime_bundle_sha256",
]
