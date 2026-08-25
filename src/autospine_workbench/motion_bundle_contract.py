"""Pure canonical two-document bundle contract for built-in MotionIR clips."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import hashlib
import json
from typing import Any

from .motion_compile_run import (
    MAX_RUN_BYTES,
    MotionCompileRunError,
    require_motion_compile_run,
)
from .motion_validation import (
    MAX_DOCUMENT_BYTES as MAX_MOTION_BYTES,
    MotionValidationError,
    motion_ir_sha256,
    require_motion_ir,
)


BUNDLE_ADDRESS_DOMAIN = b"autospine-motion-bundle-address/v1"
DOCUMENT_NAMES = ("motion.json", "run-manifest.json")
MAX_TOTAL_DOCUMENT_BYTES = MAX_MOTION_BYTES + MAX_RUN_BYTES


class MotionBundleContractError(ValueError):
    """Raised when a proposed reusable motion bundle is not exact and cross-bound."""


@dataclass(frozen=True, slots=True)
class MotionBundleContract:
    """Frozen canonical documents and their domain-separated bundle address."""

    clip_id: str
    clip_sha256: str
    run_sha256: str
    bundle_sha256: str
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
    def inventory(self) -> tuple[str, ...]:
        return tuple(name for name, _data in self._documents)


def build_motion_bundle_contract(
    motion_ir: Mapping[str, Any],
    run_manifest: Mapping[str, Any],
) -> MotionBundleContract:
    """Validate, rebuild, canonicalize, and address one built-in motion bundle."""

    try:
        require_motion_ir(motion_ir)
        require_motion_compile_run(run_manifest, motion_ir=motion_ir)
        motion_bytes = _canonical(motion_ir)
        run_bytes = _canonical(run_manifest)
        items = (
            (DOCUMENT_NAMES[0], motion_bytes),
            (DOCUMENT_NAMES[1], run_bytes),
        )
        _require_items(items)
        clip_sha = motion_ir_sha256(motion_ir)
        run_sha = _sha(run_bytes)
        return MotionBundleContract(
            clip_id=str(motion_ir["clip_id"]),
            clip_sha256=clip_sha,
            run_sha256=run_sha,
            bundle_sha256=motion_bundle_address_sha256(items),
            _documents=items,
        )
    except MotionBundleContractError:
        raise
    except (
        MotionCompileRunError,
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
    if type(value) is not tuple or len(value) != len(DOCUMENT_NAMES):
        raise MotionBundleContractError("Motion bundle document inventory is invalid")
    result = []
    for index, item in enumerate(value):
        if type(item) is not tuple or len(item) != 2:
            raise MotionBundleContractError("Motion bundle document inventory is invalid")
        name, data = item
        if name != DOCUMENT_NAMES[index] or not isinstance(data, bytes):
            raise MotionBundleContractError("Motion bundle document inventory is invalid")
        limit = MAX_MOTION_BYTES if index == 0 else MAX_RUN_BYTES
        if len(data) > limit:
            raise MotionBundleContractError(f"{name} exceeds its byte resource limit")
        result.append((name, data))
    if sum(len(data) for _name, data in result) > MAX_TOTAL_DOCUMENT_BYTES:
        raise MotionBundleContractError("Motion bundle total byte resource limit exceeded")
    return tuple(result)


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
