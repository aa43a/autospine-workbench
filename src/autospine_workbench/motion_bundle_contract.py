"""Pure canonical immutable bundle contracts for reproducible MotionIR clips."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import hashlib
import json
from typing import Any

from .bvh_motion_compile_run import (
    BvhMotionCompileRunError,
    build_bvh_motion_compile_run,
)
from .motion_compile_run import (
    MotionCompileRunError,
    require_motion_compile_run,
)
from .motion_bundle_inventory import (
    BUILTIN_DOCUMENT_NAMES,
    BVH_DOCUMENT_NAMES,
    MAX_BVH_BYTES,
    MAX_BVH_MAP_BYTES,
    MAX_BVH_RUN_BYTES,
    MAX_BVH_TOTAL_DOCUMENT_BYTES,
    MAX_MOTION_BYTES,
    MAX_RUN_BYTES,
    MAX_TOTAL_DOCUMENT_BYTES,
    MotionBundleInventoryError,
    require_document_items,
)
from .motion_validation import (
    MotionValidationError,
    motion_ir_sha256,
    require_motion_ir,
)


BUNDLE_ADDRESS_DOMAIN = b"autospine-motion-bundle-address/v1"
# Backward-compatible public name for the original built-in inventory.
DOCUMENT_NAMES = BUILTIN_DOCUMENT_NAMES


class MotionBundleContractError(ValueError):
    """Raised when a proposed reusable motion bundle is not exact and cross-bound."""


@dataclass(frozen=True, slots=True)
class MotionBundleContract:
    """Frozen canonical documents and their domain-separated bundle address."""

    clip_id: str
    clip_sha256: str
    run_sha256: str
    bundle_sha256: str
    source_kind: str
    _documents: tuple[tuple[str, bytes], ...] = field(repr=False)

    @property
    def document_bytes(self) -> dict[str, bytes]:
        return dict(self._documents)

    @property
    def motion(self) -> dict[str, Any]:
        return json.loads(dict(self._documents)["motion.json"])

    @property
    def run_manifest(self) -> dict[str, Any]:
        return json.loads(dict(self._documents)["run-manifest.json"])

    @property
    def raw_bvh(self) -> bytes | None:
        return dict(self._documents).get("source.bvh")

    @property
    def bvh_map(self) -> dict[str, Any] | None:
        data = dict(self._documents).get("map.json")
        return None if data is None else json.loads(data)

    @property
    def inventory(self) -> tuple[str, ...]:
        return tuple(name for name, _data in self._documents)


def build_motion_bundle_contract(
    motion_ir: Mapping[str, Any],
    run_manifest: Mapping[str, Any],
    *,
    raw_bvh: bytes | None = None,
    bvh_map: Mapping[str, Any] | None = None,
) -> MotionBundleContract:
    """Validate, rebuild, canonicalize, and address one exact motion bundle."""

    try:
        require_motion_ir(motion_ir)
        motion_bytes = _canonical(motion_ir)
        if raw_bvh is None and bvh_map is None:
            source_kind = "builtin"
            require_motion_compile_run(run_manifest, motion_ir=motion_ir)
            run_bytes = _canonical(run_manifest)
            items = (
                (BUILTIN_DOCUMENT_NAMES[0], motion_bytes),
                (BUILTIN_DOCUMENT_NAMES[1], run_bytes),
            )
        elif raw_bvh is not None and bvh_map is not None:
            source_kind = "bvh"
            items, run_bytes = _bvh_items(
                raw_bvh, bvh_map, motion_ir, run_manifest, motion_bytes,
            )
        else:
            raise MotionBundleContractError(
                "BVH bundle raw source and explicit map must be supplied together"
            )
        _require_items(items)
        clip_sha = motion_ir_sha256(motion_ir)
        run_sha = _sha(run_bytes)
        return MotionBundleContract(
            clip_id=str(motion_ir["clip_id"]),
            clip_sha256=clip_sha,
            run_sha256=run_sha,
            bundle_sha256=motion_bundle_address_sha256(items),
            source_kind=source_kind,
            _documents=items,
        )
    except MotionBundleContractError:
        raise
    except (
        MotionCompileRunError,
        BvhMotionCompileRunError,
        MotionValidationError,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        raise MotionBundleContractError(f"Motion bundle contract failed: {exc}") from exc


def motion_bundle_address_sha256(
    document_items: tuple[tuple[str, bytes], ...],
) -> str:
    """Hash exact ordered filename/length/byte frames under a motion-only domain."""

    items = _require_items(document_items)
    digest = hashlib.sha256()
    _feed(digest, BUNDLE_ADDRESS_DOMAIN)
    digest.update(len(items).to_bytes(4, "big"))
    for name, data in items:
        _feed(digest, name.encode("utf-8"))
        _feed(digest, data)
    return digest.hexdigest()


def _require_items(
    value: tuple[tuple[str, bytes], ...],
) -> tuple[tuple[str, bytes], ...]:
    try:
        names = tuple(
            item[0] for item in value
            if type(item) is tuple and len(item) == 2
        ) if type(value) is tuple else ()
        return require_document_items(
            value,
            limit_by_name={
                "source.bvh": MAX_BVH_BYTES,
                "map.json": MAX_BVH_MAP_BYTES,
                "motion.json": MAX_MOTION_BYTES,
                "run-manifest.json": (
                    MAX_RUN_BYTES
                    if names == BUILTIN_DOCUMENT_NAMES
                    else MAX_BVH_RUN_BYTES
                ),
            },
            total_by_kind={
                "builtin": MAX_TOTAL_DOCUMENT_BYTES,
                "bvh": MAX_BVH_TOTAL_DOCUMENT_BYTES,
            },
        )
    except MotionBundleInventoryError as exc:
        raise MotionBundleContractError(str(exc)) from exc


def _feed(digest, value: bytes) -> None:
    digest.update(len(value).to_bytes(8, "big"))
    digest.update(value)


def _canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        dict(value), ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _bvh_items(raw_bvh, bvh_map, motion_ir, run_manifest, motion_bytes):
    if type(raw_bvh) is not bytes:
        raise MotionBundleContractError("BVH source must be immutable bytes")
    map_bytes = _canonical(bvh_map)
    rebuilt = build_bvh_motion_compile_run(raw_bvh, bvh_map, motion_ir)
    supplied_run = _canonical(run_manifest)
    if supplied_run != rebuilt.canonical_bytes:
        raise MotionBundleContractError(
            "BVH compile run differs from exact source recompile"
        )
    return (
        ("source.bvh", raw_bvh),
        ("map.json", map_bytes),
        ("motion.json", motion_bytes),
        ("run-manifest.json", supplied_run),
    ), supplied_run
