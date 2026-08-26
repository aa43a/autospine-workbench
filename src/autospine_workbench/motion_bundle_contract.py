"""Pure canonical immutable bundle contracts for reproducible MotionIR clips."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import hashlib
import json
from typing import Any

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
    KIMODO_DOCUMENT_NAMES,
    MAX_KIMODO_MAP_BYTES,
    MAX_KIMODO_RUN_BYTES,
    MAX_KIMODO_SOURCE_BYTES,
    MAX_KIMODO_TOTAL_DOCUMENT_BYTES,
    MAX_RAW_NPZ_BYTES,
    MotionBundleInventoryError,
    require_document_items,
)
from .motion_bundle_source_builders import (
    MotionBundleSourceError,
    build_motion_source_documents,
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
        documents = dict(self._documents)
        data = documents.get("map.json") if "source.bvh" in documents else None
        return None if data is None else json.loads(data)

    @property
    def raw_npz(self) -> bytes | None:
        return dict(self._documents).get("source.npz")

    @property
    def kimodo_source(self) -> dict[str, Any] | None:
        data = dict(self._documents).get("sidecar.json")
        return None if data is None else json.loads(data)

    @property
    def kimodo_map(self) -> dict[str, Any] | None:
        documents = dict(self._documents)
        data = documents.get("map.json") if "source.npz" in documents else None
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
    raw_npz: bytes | None = None,
    kimodo_source: Mapping[str, Any] | None = None,
    kimodo_map: Mapping[str, Any] | None = None,
) -> MotionBundleContract:
    """Validate, rebuild, canonicalize, and address one exact motion bundle."""

    try:
        require_motion_ir(motion_ir)
        motion_bytes = _canonical(motion_ir)
        source_documents = build_motion_source_documents(
            motion_ir, run_manifest, motion_bytes,
            raw_bvh=raw_bvh, bvh_map=bvh_map,
            raw_npz=raw_npz, kimodo_source=kimodo_source,
            kimodo_map=kimodo_map,
        )
        source_kind = source_documents.source_kind
        items, run_bytes = source_documents.items, source_documents.run_bytes
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
        MotionBundleSourceError,
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
                "map.json": (
                    MAX_KIMODO_MAP_BYTES
                    if names == KIMODO_DOCUMENT_NAMES else MAX_BVH_MAP_BYTES
                ),
                "motion.json": MAX_MOTION_BYTES,
                "run-manifest.json": (
                    MAX_RUN_BYTES
                    if names == BUILTIN_DOCUMENT_NAMES
                    else MAX_KIMODO_RUN_BYTES
                    if names == KIMODO_DOCUMENT_NAMES
                    else MAX_BVH_RUN_BYTES
                ),
                "source.npz": MAX_RAW_NPZ_BYTES,
                "sidecar.json": MAX_KIMODO_SOURCE_BYTES,
            },
            total_by_kind={
                "builtin": MAX_TOTAL_DOCUMENT_BYTES,
                "bvh": MAX_BVH_TOTAL_DOCUMENT_BYTES,
                "kimodo_npz": MAX_KIMODO_TOTAL_DOCUMENT_BYTES,
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
