"""Auditable domain-separated identity for one body-sway candidate."""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
import re
from typing import Any


_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_DOMAIN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,127}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_BODY_ID = re.compile(r"^body-sway-[0-9a-f]{64}$")


def body_sway_candidate_id(
    *,
    generator: Mapping[str, Any],
    motion_instance_v2_sha256: str,
    target_profile_sha256: str,
    feature_id: str,
    target_bone_ids: list[str],
) -> str:
    """Hash only document-visible values, including the target profile seal."""

    if not isinstance(generator, Mapping) or set(generator) != {
        "id", "version", "candidate_id_domain",
    }:
        raise ValueError("Idle candidate generator identity is invalid")
    for field in ("id", "version"):
        if not isinstance(generator.get(field), str) \
                or not _ID.fullmatch(generator[field]):
            raise ValueError("Idle candidate generator identity is invalid")
    domain = generator.get("candidate_id_domain")
    if not isinstance(domain, str) or not _DOMAIN.fullmatch(domain):
        raise ValueError("Idle candidate domain is invalid")
    if not isinstance(feature_id, str) or not _ID.fullmatch(feature_id):
        raise ValueError("Idle candidate feature id is invalid")
    for value in (motion_instance_v2_sha256, target_profile_sha256):
        if not isinstance(value, str) or not _SHA.fullmatch(value):
            raise ValueError("Idle candidate source SHA is invalid")
    if not isinstance(target_bone_ids, list) or not target_bone_ids \
            or any(not isinstance(item, str) or not _ID.fullmatch(item)
                   for item in target_bone_ids) \
            or len(target_bone_ids) != len(set(target_bone_ids)):
        raise ValueError("Idle candidate target bone inventory is invalid")
    payload = {
        "feature_id": feature_id,
        "generator": {
            "id": generator["id"], "version": generator["version"],
        },
        "motion_instance_v2_sha256": motion_instance_v2_sha256,
        "target_profile_sha256": target_profile_sha256,
        "target_bone_ids": target_bone_ids,
    }
    digest = hashlib.sha256()
    _feed(digest, generator["candidate_id_domain"].encode("ascii"))
    _feed(digest, _canonical(payload))
    return f"body-sway-{digest.hexdigest()}"


def require_candidate_id_binding(document: Mapping[str, Any]) -> None:
    """Recompute the sole candidate ID from its standalone document."""

    row = document["features"][1]
    if row["availability"] != "candidate":
        return
    candidate_id = row["candidate_id"]
    if not isinstance(candidate_id, str) or not _BODY_ID.fullmatch(candidate_id):
        raise ValueError("Body-sway candidate id format is invalid")
    expected = body_sway_candidate_id(
        generator=document["generator"],
        motion_instance_v2_sha256=document["source"]["p9"][
            "motion_instance_v2_sha256"
        ],
        target_profile_sha256=document["source"]["p5"][
            "target_profile_sha256"
        ],
        feature_id=row["feature_id"],
        target_bone_ids=row["proposal"]["target_bone_ids"],
    )
    if candidate_id != expected:
        raise ValueError("Body-sway candidate id binding is stale")


def _feed(digest, value: bytes) -> None:
    digest.update(len(value).to_bytes(8, "big"))
    digest.update(value)


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
