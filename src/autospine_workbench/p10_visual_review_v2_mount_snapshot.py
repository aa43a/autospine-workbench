"""Strict canonical codec for persistent P10.3c v2 mount snapshots."""

from __future__ import annotations

import base64
import binascii
import json
from pathlib import Path

from .capture_framing_candidate import CaptureFramingCandidate
from .capture_framing_validation import (
    capture_framing_candidate_sha256,
    require_capture_framing_candidate,
)
from .idle_behavior_candidate_validation import (
    idle_behavior_candidates_sha256,
    require_idle_behavior_candidates,
)
from .idle_behavior_candidates import IdleBehaviorCandidates
from .idle_behavior_review_address import IdleBehaviorReviewAddress
from .manifest_artifacts import require_sha256
from .p10_preview_v2_cache import (
    P10PreviewV2CacheKey, P10PreviewV2CacheLocator,
    P10PreviewV2CacheRecord,
)
from .p10_preview_v2_result import P10PreviewV2CommandResult
from .temporary_body_sway_preview_artifacts import (
    ARTIFACT_PATHS, MAX_ARTIFACT_BYTES,
)
from .temporary_body_sway_preview_v2 import TemporaryBodySwayPreviewV2
from .temporary_body_sway_preview_validation_v2 import (
    require_temporary_body_sway_preview_v2,
    temporary_body_sway_preview_sha256_v2,
)


FORMAT = "autospine-p10-visual-review-v2-mount-cache"
FORMAT_VERSION = 3
_TOP = {
    "format", "format_version", "job_id", "package_id",
    "preview_compiler_sha256", "cache_key", "address",
    "idle_behavior_candidates", "capture_framing_candidate", "preview",
    "result",
}
_KEY = {
    "inventory_sha256", "p10_candidate_sha256", "p10_decision_sha256",
    "p10_revision", "framing_candidate_sha256",
    "framing_decision_sha256", "framing_revision",
}
_RESULT = {
    "package_id", "project_id", "clip_id", "temporary_preview_v2_sha256",
    "artifact_set_sha256", "capture_framing_candidate_sha256",
    "capture_framing_decision_sha256", "capture_framing_revision",
    "case_count",
}


class MountSnapshotError(ValueError):
    """Raised when cached detached values are malformed or cross-wired."""


def mount_snapshot_document(job_id, record) -> dict:
    if type(record) is not P10PreviewV2CacheRecord:
        raise MountSnapshotError("Snapshot requires a Preview v2 record")
    _validate_record(
        record, job_id, record.key.locator,
        record.result.temporary_preview_v2_sha256,
        record.result.artifact_set_sha256,
    )
    preview = record.result._preview
    return {
        "format": FORMAT, "format_version": FORMAT_VERSION,
        "job_id": job_id, "package_id": record.key.locator.package_id,
        "preview_compiler_sha256":
            record.key.locator.compiler_inventory_sha256,
        "cache_key": {name: getattr(record.key, name) for name in _KEY},
        "address": record.address.public_document(),
        "idle_behavior_candidates": record.candidates.document,
        "capture_framing_candidate": record.framing_candidate.document,
        "preview": {
            "manifest": preview.document,
            "manifest_sha256": preview.sha256,
            "artifact_set_sha256": preview.artifact_set_sha256,
            "artifacts": [{
                "path": path,
                "base64": base64.b64encode(
                    preview.artifact_bytes[path]
                ).decode("ascii"),
            } for path in ARTIFACT_PATHS],
        },
        "result": _result_document(record.result),
    }


def record_from_mount_snapshot(
    document, job_id, locator, expected_preview_sha, expected_artifact_sha,
):
    _fields(document, _TOP)
    compiler_sha = require_sha256(
        document["preview_compiler_sha256"], "Snapshot preview compiler",
    )
    if compiler_sha != locator.compiler_inventory_sha256:
        raise MountSnapshotError("Snapshot preview compiler differs")
    if document["format"] != FORMAT \
            or document["format_version"] != FORMAT_VERSION \
            or document["job_id"] != job_id \
            or document["package_id"] != locator.package_id:
        raise MountSnapshotError("Snapshot envelope differs")
    key = _key(_mapping(document["cache_key"]), locator)
    address = IdleBehaviorReviewAddress(**_mapping(document["address"]))
    candidates_doc = _mapping(document["idle_behavior_candidates"])
    framing_doc = _mapping(document["capture_framing_candidate"])
    require_idle_behavior_candidates(candidates_doc)
    require_capture_framing_candidate(framing_doc)
    preview_row = _mapping(document["preview"])
    _fields(preview_row, {
        "manifest", "manifest_sha256", "artifact_set_sha256", "artifacts",
    })
    artifacts = _artifacts(preview_row["artifacts"])
    preview_doc = _mapping(preview_row["manifest"])
    preview = TemporaryBodySwayPreviewV2(
        canonical_mount_snapshot(preview_doc).decode("utf-8"),
        tuple(sorted(artifacts.items())),
    )
    result_row = _mapping(document["result"])
    _fields(result_row, _RESULT)
    result = P10PreviewV2CommandResult(
        **result_row, _preview=preview,
        _workspace_root=Path(locator.workspace_root),
        _state_root=Path(locator.state_root),
    )
    record = P10PreviewV2CacheRecord(
        key, address,
        IdleBehaviorCandidates(
            canonical_mount_snapshot(candidates_doc).decode("utf-8")
        ),
        CaptureFramingCandidate(
            canonical_mount_snapshot(framing_doc).decode("utf-8")
        ),
        result,
    )
    if preview_row["manifest_sha256"] != preview.sha256 \
            or preview_row["artifact_set_sha256"] != preview.artifact_set_sha256:
        raise MountSnapshotError("Snapshot preview seals differ")
    _validate_record(
        record, job_id, locator,
        expected_preview_sha, expected_artifact_sha,
    )
    return record


def _validate_record(record, job_id, locator, preview_sha, artifact_sha):
    if type(record.key) is not P10PreviewV2CacheKey \
            or record.key.locator != locator \
            or type(record.address) is not IdleBehaviorReviewAddress \
            or type(record.candidates) is not IdleBehaviorCandidates \
            or type(record.framing_candidate) is not CaptureFramingCandidate \
            or type(record.result) is not P10PreviewV2CommandResult:
        raise MountSnapshotError("Snapshot record types differ")
    require_sha256(job_id, "Mount cache job")
    candidates, framing = record.candidates, record.framing_candidate
    require_idle_behavior_candidates(candidates.document)
    require_capture_framing_candidate(framing.document)
    preview = record.result._preview
    require_temporary_body_sway_preview_v2(
        preview.document, preview.artifact_bytes,
    )
    key, result, source = record.key, record.result, preview.document["source"]
    head = source["current_p10_1_head"]
    expected_result = {
        "package_id": locator.package_id,
        "project_id": preview.document["project_id"],
        "clip_id": preview.document["clip_id"],
        "temporary_preview_v2_sha256": preview.sha256,
        "artifact_set_sha256": preview.artifact_set_sha256,
        "capture_framing_candidate_sha256": framing.sha256,
        "capture_framing_decision_sha256": key.framing_decision_sha256,
        "capture_framing_revision": key.framing_revision,
        "case_count": len(preview.document["capture_plan"]["cases"]),
    }
    hashes_match = (
        preview.sha256 == preview_sha
        and preview.artifact_set_sha256 == artifact_sha
        and temporary_body_sway_preview_sha256_v2(
            preview.document, preview.artifact_bytes,
        ) == preview_sha
        and idle_behavior_candidates_sha256(candidates.document)
        == key.p10_candidate_sha256
        and capture_framing_candidate_sha256(framing.document)
        == key.framing_candidate_sha256
    )
    if _result_document(result) != expected_result or not hashes_match \
            or (head["candidate_sha256"], head["decision_sha256"],
                head["revision"]) != (
                    key.p10_candidate_sha256, key.p10_decision_sha256,
                    key.p10_revision,
                ):
        raise MountSnapshotError("Snapshot record identities differ")
    _cross_bind(record, source)


def _cross_bind(record, source):
    address, candidates = record.address, record.candidates.document
    framing, key = record.framing_candidate.document, record.key
    p9 = candidates["source"]["p9"]
    projects = {
        address.project_id, candidates["project_id"], framing["project_id"],
        record.result.project_id,
    }
    clips = {
        address.clip_id, candidates["clip_id"], framing["clip_id"],
        record.result.clip_id,
    }
    framing_source = framing["source"]
    if len(projects) != 1 or len(clips) != 1 \
            or address.package_id != key.locator.package_id \
            or framing_source["package_id"] != address.package_id \
            or source["idle_behavior_candidates_sha256"] \
                != record.candidates.sha256 \
            or source["capture_framing_candidate_sha256"] \
                != record.framing_candidate.sha256 \
            or (source["capture_framing_decision_sha256"],
                source["capture_framing_revision"]) \
                != (key.framing_decision_sha256, key.framing_revision) \
            or framing_source["current_p10_1_head"] \
                != source["current_p10_1_head"] \
            or (p9["motion_instance_v2_sha256"], p9["bundle_sha256"],
                p9["motion_policy_decision_sha256"]) != (
                    address.motion_instance_v2_sha256,
                    address.reviewed_motion_bundle_sha256,
                    address.p9_decision_sha256,
                ):
        raise MountSnapshotError("Snapshot sources are cross-wired")


def _key(row, locator):
    _fields(row, _KEY)
    for name in _KEY - {"p10_revision", "framing_revision"}:
        require_sha256(row[name], name)
    if type(row["p10_revision"]) is not int \
            or not 1 <= row["p10_revision"] <= 10_000 \
            or type(row["framing_revision"]) is not int \
            or not 1 <= row["framing_revision"] <= 64:
        raise MountSnapshotError("Snapshot revisions differ")
    return P10PreviewV2CacheKey(locator, **row)


def _result_document(result):
    return {name: getattr(result, name) for name in _RESULT}


def _artifacts(value):
    if type(value) is not list or len(value) != len(ARTIFACT_PATHS):
        raise MountSnapshotError("Snapshot artifact inventory differs")
    result = {}
    for path, row in zip(ARTIFACT_PATHS, value, strict=True):
        row = _mapping(row)
        _fields(row, {"path", "base64"})
        encoded = row["base64"]
        if row["path"] != path or type(encoded) is not str \
                or len(encoded) > 4 * ((MAX_ARTIFACT_BYTES + 2) // 3):
            raise MountSnapshotError("Snapshot artifact row differs")
        try:
            raw = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise MountSnapshotError("Snapshot base64 is invalid") from exc
        if base64.b64encode(raw).decode("ascii") != encoded:
            raise MountSnapshotError("Snapshot base64 is non-canonical")
        result[path] = raw
    if sum(map(len, result.values())) > MAX_ARTIFACT_BYTES:
        raise MountSnapshotError("Snapshot artifacts exceed their byte limit")
    return result


def _fields(value, expected):
    if type(value) is not dict or set(value) != set(expected):
        raise MountSnapshotError("Snapshot fields differ")


def _mapping(value):
    if type(value) is not dict:
        raise MountSnapshotError("Snapshot value is not an object")
    return value


def canonical_mount_snapshot(value) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")


__all__ = [
    "MountSnapshotError", "canonical_mount_snapshot",
    "mount_snapshot_document", "record_from_mount_snapshot",
]
