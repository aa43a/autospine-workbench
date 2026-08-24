"""Shared content identities and source hashes for candidate providers."""

from __future__ import annotations

import hashlib
from pathlib import Path
import re
from typing import Any, Mapping

from .resolved_project import canonical_sha256


_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def required_sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError(f"{label} SHA-256 is missing or invalid")
    return value


def sha256_file(path: Path, label: str = "evidence asset") -> str:
    try:
        with Path(path).open("rb") as handle:
            return hashlib.file_digest(handle, "sha256").hexdigest()
    except OSError as exc:
        raise ValueError(f"Cannot hash {label}: {Path(path).name}") from exc


def candidate_run_identity(
    project: Mapping[str, Any],
    *,
    provider_id: str,
    provider_version: str,
    config: Mapping[str, Any],
    evidence_identity: Mapping[str, Any],
) -> dict[str, str]:
    raw_resolved = project.get("resolved")
    if raw_resolved is not None and not isinstance(raw_resolved, Mapping):
        raise ValueError("resolved snapshot must be an object")
    resolved = raw_resolved or {}
    resolved_sha = (
        required_sha256(resolved.get("sha256"), "resolved snapshot")
        if resolved
        else None
    )
    input_sha = canonical_sha256(
        {
            "project_id": project.get("id"),
            "source": project.get("source"),
            "canvas": project.get("canvas"),
            "resolved_revision": resolved.get("revision"),
            "resolved_snapshot_sha256": resolved_sha,
            "skeleton": project.get("skeleton"),
            "evidence": evidence_identity,
        }
    )
    config_sha = canonical_sha256(config)
    run_sha = canonical_sha256(
        {
            "input_sha256": input_sha,
            "provider": provider_id,
            "provider_version": provider_version,
            "config_sha256": config_sha,
        }
    )
    return {"input_sha256": input_sha, "config_sha256": config_sha, "run_sha256": run_sha}
