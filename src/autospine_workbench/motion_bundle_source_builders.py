"""Source-kind dispatch for exact MotionIR bundle document construction."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
from typing import Any

from .bvh_motion_compile_run import build_bvh_motion_compile_run
from .kimodo_npz_compile_run import build_kimodo_npz_compile_run
from .motion_compile_run import require_motion_compile_run
from .motion_bundle_inventory import (
    BUILTIN_DOCUMENT_NAMES,
    BVH_DOCUMENT_NAMES,
    KIMODO_DOCUMENT_NAMES,
)


class MotionBundleSourceError(ValueError):
    """Raised when source-family inputs are incomplete, mixed, or unreproducible."""


@dataclass(frozen=True, slots=True)
class MotionBundleSourceDocuments:
    source_kind: str
    items: tuple[tuple[str, bytes], ...]
    run_bytes: bytes


def build_motion_source_documents(
    motion_ir: Mapping[str, Any],
    run_manifest: Mapping[str, Any],
    motion_bytes: bytes,
    *,
    raw_bvh: bytes | None,
    bvh_map: Mapping[str, Any] | None,
    raw_npz: bytes | None,
    kimodo_source: Mapping[str, Any] | None,
    kimodo_map: Mapping[str, Any] | None,
) -> MotionBundleSourceDocuments:
    """Select exactly one source family and rebuild its compile run."""

    bvh = (raw_bvh, bvh_map)
    kimodo = (raw_npz, kimodo_source, kimodo_map)
    has_bvh, has_kimodo = any(value is not None for value in bvh), any(
        value is not None for value in kimodo
    )
    if has_bvh and has_kimodo:
        raise MotionBundleSourceError("Motion bundle source families cannot be mixed")
    if has_bvh:
        if not all(value is not None for value in bvh):
            raise MotionBundleSourceError(
                "BVH bundle raw source and explicit map must be supplied together"
            )
        return _bvh(raw_bvh, bvh_map, motion_ir, run_manifest, motion_bytes)
    if has_kimodo:
        if not all(value is not None for value in kimodo):
            raise MotionBundleSourceError(
                "Kimodo bundle raw source, sidecar, and map must be supplied together"
            )
        return _kimodo(
            raw_npz, kimodo_source, kimodo_map,
            motion_ir, run_manifest, motion_bytes,
        )
    require_motion_compile_run(run_manifest, motion_ir=motion_ir)
    run_bytes = _canonical(run_manifest)
    return MotionBundleSourceDocuments(
        "builtin",
        (
            (BUILTIN_DOCUMENT_NAMES[0], motion_bytes),
            (BUILTIN_DOCUMENT_NAMES[1], run_bytes),
        ),
        run_bytes,
    )


def _bvh(raw_bvh, bvh_map, motion_ir, run_manifest, motion_bytes):
    if type(raw_bvh) is not bytes:
        raise MotionBundleSourceError("BVH source must be immutable bytes")
    map_bytes = _canonical(bvh_map)
    rebuilt = build_bvh_motion_compile_run(raw_bvh, bvh_map, motion_ir)
    run_bytes = _same_run(run_manifest, rebuilt.canonical_bytes, "BVH")
    return MotionBundleSourceDocuments(
        "bvh",
        tuple(zip(BVH_DOCUMENT_NAMES, (
            raw_bvh, map_bytes, motion_bytes, run_bytes,
        ))),
        run_bytes,
    )


def _kimodo(
    raw_npz, source, mapping, motion_ir, run_manifest, motion_bytes,
):
    if type(raw_npz) is not bytes:
        raise MotionBundleSourceError("Kimodo NPZ source must be immutable bytes")
    source_bytes, map_bytes = _canonical(source), _canonical(mapping)
    rebuilt = build_kimodo_npz_compile_run(
        raw_npz, source, mapping, motion_ir
    )
    run_bytes = _same_run(run_manifest, rebuilt.canonical_bytes, "Kimodo")
    return MotionBundleSourceDocuments(
        "kimodo_npz",
        tuple(zip(KIMODO_DOCUMENT_NAMES, (
            raw_npz, source_bytes, map_bytes, motion_bytes, run_bytes,
        ))),
        run_bytes,
    )


def _same_run(
    run_manifest: Mapping[str, Any], expected: bytes, label: str
) -> bytes:
    supplied = _canonical(run_manifest)
    if supplied != expected:
        raise MotionBundleSourceError(
            f"{label} compile run differs from exact source recompile"
        )
    return supplied


def _canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        dict(value), ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
