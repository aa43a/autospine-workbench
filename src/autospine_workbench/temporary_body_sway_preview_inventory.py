"""Strict byte inventory and domain-separated seal for five preview files."""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
import re
from typing import Any

from .body_sway_preview_profile import ARTIFACT_SET_DIGEST_DOMAIN
from .resolved_project import canonical_sha256
from .temporary_body_sway_preview_artifacts import (
    ARTIFACT_PATHS,
    MAX_ARTIFACT_BYTES,
    MAX_ATLAS_BYTES,
    MAX_SKELETON_BYTES,
    MAX_SMALL_FILE_BYTES,
    MAX_TEXTURE_BYTES,
)


_DESCRIPTORS = {
    "runtime/player.html": ("preview-player", "text/html; charset=utf-8"),
    "runtime/session.json": ("preview-session", "application/json"),
    "runtime/skeleton.atlas": (
        "spine-atlas", "text/plain; charset=utf-8",
    ),
    "runtime/skeleton.json": ("spine-skeleton", "application/json"),
    "runtime/skeleton.png": ("spine-texture", "image/png"),
}
_LIMITS = {
    "runtime/player.html": MAX_SMALL_FILE_BYTES,
    "runtime/session.json": MAX_SMALL_FILE_BYTES,
    "runtime/skeleton.atlas": MAX_ATLAS_BYTES,
    "runtime/skeleton.json": MAX_SKELETON_BYTES,
    "runtime/skeleton.png": MAX_TEXTURE_BYTES,
}
_SHA = re.compile(r"^[0-9a-f]{64}$")


class TemporaryBodySwayPreviewInventoryError(ValueError):
    """Raised when the exact five-file byte inventory is inconsistent."""


def build_temporary_body_sway_preview_inventory(
    artifacts: Mapping[str, bytes],
) -> dict[str, Any]:
    """Build a sorted, bounded inventory and its artifact-set seal."""

    if not isinstance(artifacts, Mapping) \
            or tuple(sorted(artifacts)) != ARTIFACT_PATHS:
        raise TemporaryBodySwayPreviewInventoryError(
            "Temporary preview requires exactly five fixed artifact paths"
        )
    files = []
    total = 0
    for path in ARTIFACT_PATHS:
        raw = artifacts[path]
        if type(raw) is not bytes or not raw or len(raw) > _LIMITS[path]:
            raise TemporaryBodySwayPreviewInventoryError(
                f"Temporary preview artifact is invalid or oversized: {path}"
            )
        role, media_type = _DESCRIPTORS[path]
        total += len(raw)
        files.append({
            "path": path,
            "role": role,
            "media_type": media_type,
            "size_bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
        })
    if total > MAX_ARTIFACT_BYTES:
        raise TemporaryBodySwayPreviewInventoryError(
            "Temporary preview artifact set exceeds its byte limit"
        )
    return {
        "artifact_set_sha256": canonical_sha256({
            "domain": ARTIFACT_SET_DIGEST_DOMAIN, "files": files,
        }),
        "files": files,
    }


def require_temporary_body_sway_preview_inventory(
    value: Any,
) -> tuple[dict[str, Any], ...]:
    """Validate standalone fields, order, bounds, and artifact-set digest."""

    if not isinstance(value, Mapping) \
            or set(value) != {"artifact_set_sha256", "files"} \
            or not isinstance(value.get("files"), list) \
            or len(value["files"]) != len(ARTIFACT_PATHS):
        raise TemporaryBodySwayPreviewInventoryError(
            "Temporary preview artifact inventory fields are invalid"
        )
    files, total = [], 0
    for path, raw in zip(ARTIFACT_PATHS, value["files"], strict=True):
        if not isinstance(raw, Mapping) or set(raw) != {
            "path", "role", "media_type", "size_bytes", "sha256",
        }:
            raise TemporaryBodySwayPreviewInventoryError(
                "Temporary preview artifact row fields are invalid"
            )
        role, media_type = _DESCRIPTORS[path]
        size = raw.get("size_bytes")
        if raw.get("path") != path or raw.get("role") != role \
                or raw.get("media_type") != media_type \
                or type(size) is not int or not 1 <= size <= _LIMITS[path] \
                or not isinstance(raw.get("sha256"), str) \
                or not _SHA.fullmatch(raw["sha256"]):
            raise TemporaryBodySwayPreviewInventoryError(
                f"Temporary preview artifact row is invalid: {path}"
            )
        total += size
        files.append(dict(raw))
    if total > MAX_ARTIFACT_BYTES:
        raise TemporaryBodySwayPreviewInventoryError(
            "Temporary preview artifact total exceeds its byte limit"
        )
    expected = canonical_sha256({
        "domain": ARTIFACT_SET_DIGEST_DOMAIN, "files": files,
    })
    if value.get("artifact_set_sha256") != expected:
        raise TemporaryBodySwayPreviewInventoryError(
            "Temporary preview artifact-set digest is inconsistent"
        )
    return tuple(files)
