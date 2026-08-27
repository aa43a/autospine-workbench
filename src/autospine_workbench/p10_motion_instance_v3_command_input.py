"""Strict input boundary for the P10.6b compile command."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .manifest_artifacts import require_sha256
from .motion_instance_v3_bundle_contract import MAX_ADMISSION_BYTES
from .safe_input_files import read_real_file, strict_json_object
from .seam_anchor_review_json import canonical_json_bytes


MAX_WRAPPER_BYTES = MAX_ADMISSION_BYTES + 2 * 1024 * 1024
_WRAPPER_FIELDS = {
    "ok",
    "status",
    "project_id",
    "clip_id",
    "dynamic_seam_probe_sha256",
    "reviewed_motion_address",
    "body_sway_motion_consumer_admission_sha256",
    "admission",
    "head_observation",
}
_P9_FIELDS = {
    "motion_instance_v2_sha256",
    "reviewed_motion_bundle_sha256",
}


def read_admission_wrapper(
    path: Path,
    project_id: str,
    admission_sha256: str,
) -> dict[str, Any]:
    """Read one canonical successful P10.6a CLI wrapper."""

    raw = read_real_file(
        Path(path),
        MAX_WRAPPER_BYTES,
        "P10.6a motion-consumer admission CLI wrapper",
    )
    wrapper = strict_json_object(
        raw, "P10.6a motion-consumer admission CLI wrapper"
    )
    canonical = canonical_json_bytes(wrapper)
    if raw not in (canonical, canonical + b"\n", canonical + b"\r\n"):
        raise ValueError("admission wrapper is not canonical CLI JSON")
    if (
        set(wrapper) != _WRAPPER_FIELDS
        or wrapper.get("ok") is not True
        or wrapper.get("status") != "compiled"
        or wrapper.get("project_id") != project_id
    ):
        raise ValueError("admission wrapper fields are unsupported")

    explicit = require_sha256(
        admission_sha256, "Body-sway motion-consumer admission digest"
    )
    if wrapper.get("body_sway_motion_consumer_admission_sha256") != explicit:
        raise ValueError("admission wrapper differs from explicit address")

    admission = wrapper.get("admission")
    if (
        type(admission) is not dict
        or admission.get("project_id") != project_id
        or admission.get("clip_id") != wrapper.get("clip_id")
    ):
        raise ValueError("admission wrapper identity is cross-wired")
    _require_wrapper_sources(wrapper, admission)
    return wrapper


def _require_wrapper_sources(
    wrapper: dict[str, Any],
    admission: dict[str, Any],
) -> None:
    source = admission["source"]
    p9 = source["p9"]
    address = wrapper.get("reviewed_motion_address")
    expected_address = {
        "motion_instance_v2_sha256": p9["motion_instance_v2_sha256"],
        "reviewed_motion_bundle_sha256": p9["bundle_sha256"],
    }
    if (
        type(address) is not dict
        or set(address) != _P9_FIELDS
        or address != expected_address
    ):
        raise ValueError("admission wrapper P9 address is cross-wired")
    if (
        wrapper.get("dynamic_seam_probe_sha256")
        != source["dynamic_seam_probe_sha256"]
    ):
        raise ValueError("admission wrapper probe identity is cross-wired")

    heads = admission["head_observations"]
    expected_head = {
        "method": "outer-before-after-consumer-core-compilation",
        "scope": "compile_time",
        "before": heads["before"]["observation"],
        "after": heads["after"]["observation"],
        "checks": {
            "before_after_identity": "exact_match",
            "before_after_documents": "canonical_bytes_exact_match",
        },
        "permanent_authority_claimed": False,
    }
    if wrapper.get("head_observation") != expected_head:
        raise ValueError("admission wrapper head evidence is cross-wired")


__all__ = ["MAX_WRAPPER_BYTES", "read_admission_wrapper"]
