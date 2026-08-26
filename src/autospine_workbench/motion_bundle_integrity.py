"""Reproducibility verification for one snapshotted immutable motion bundle."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any

from .motion_bundle_contract import (
    MotionBundleContractError,
    build_motion_bundle_contract,
)
from .motion_bundle_inventory import (
    MotionBundleInventoryError,
    profile_for_ordered_names,
)
from .motion_compile_run import (
    MotionCompileRunError,
    build_builtin_motion_compile_run,
    require_motion_compile_run,
)
from .motion_validation import (
    MotionValidationError,
    require_motion_ir,
)


class MotionBundleIntegrityError(ValueError):
    """Raised when stored motion bytes cannot be exactly reproduced."""


@dataclass(frozen=True, slots=True)
class MotionBundleSnapshot:
    """The single admitted read of every file in a secured bundle directory."""

    directory: Path
    document_items: tuple[tuple[str, bytes], ...] = field(repr=False)


@dataclass(frozen=True, slots=True)
class VerifiedMotionBundle:
    """Frozen verified identities with fresh document and byte accessors."""

    path: Path
    clip_id: str
    clip_sha256: str
    run_sha256: str
    bundle_sha256: str
    source_kind: str
    _document_items: tuple[tuple[str, bytes], ...] = field(repr=False)

    def _document(self, name: str) -> dict[str, Any]:
        return json.loads(dict(self._document_items)[name])

    @property
    def motion(self) -> dict[str, Any]:
        return self._document("motion.json")

    @property
    def run_manifest(self) -> dict[str, Any]:
        return self._document("run-manifest.json")

    @property
    def raw_bvh(self) -> bytes | None:
        return dict(self._document_items).get("source.bvh")

    @property
    def bvh_map(self) -> dict[str, Any] | None:
        documents = dict(self._document_items)
        if "source.bvh" not in documents:
            return None
        return self._document("map.json")

    @property
    def raw_npz(self) -> bytes | None:
        return dict(self._document_items).get("source.npz")

    @property
    def kimodo_source(self) -> dict[str, Any] | None:
        if "sidecar.json" not in dict(self._document_items):
            return None
        return self._document("sidecar.json")

    @property
    def kimodo_map(self) -> dict[str, Any] | None:
        if "source.npz" not in dict(self._document_items):
            return None
        return self._document("map.json")

    @property
    def document_bytes(self) -> dict[str, bytes]:
        return dict(self._document_items)

    @property
    def inventory(self) -> tuple[str, ...]:
        return tuple(name for name, _data in self._document_items)


def verify_motion_bundle_snapshot(
    snapshot: MotionBundleSnapshot,
    *,
    expected_clip_sha256: str,
    expected_bundle_sha256: str,
) -> VerifiedMotionBundle:
    """Decode strict bytes and rebuild their run and bundle content addresses."""

    try:
        if not isinstance(snapshot, MotionBundleSnapshot):
            raise MotionBundleIntegrityError("Motion bundle snapshot is invalid")
        raw, source_kind = _exact_items(snapshot.document_items)
        json_names = tuple(
            name for name in raw if name not in {"source.bvh", "source.npz"}
        )
        documents = {name: _strict_json(raw[name], name) for name in json_names}
        motion = documents["motion.json"]
        stored_run = documents["run-manifest.json"]
        if source_kind == "builtin":
            clip_id, contract, rebuilt_run_sha = _rebuild_builtin(
                motion, stored_run,
            )
        elif source_kind == "bvh":
            clip_id, contract, rebuilt_run_sha = _rebuild_bvh(
                raw["source.bvh"], documents["map.json"], motion, stored_run,
            )
        else:
            clip_id, contract, rebuilt_run_sha = _rebuild_kimodo(
                raw["source.npz"], documents["sidecar.json"],
                documents["map.json"], motion, stored_run,
            )
        if (
            contract.run_sha256 != rebuilt_run_sha
            or contract.document_bytes != raw
        ):
            raise MotionBundleIntegrityError(
                "Motion bundle bytes differ from their exact rebuilt snapshots"
            )
        if (
            contract.clip_id != clip_id
            or contract.clip_sha256 != expected_clip_sha256
            or contract.bundle_sha256 != expected_bundle_sha256
        ):
            raise MotionBundleIntegrityError(
                "Motion bundle differs from its requested content address"
            )
        _require_address(snapshot.directory, contract)
        return VerifiedMotionBundle(
            path=snapshot.directory,
            clip_id=clip_id,
            clip_sha256=contract.clip_sha256,
            run_sha256=contract.run_sha256,
            bundle_sha256=contract.bundle_sha256,
            source_kind=source_kind,
            _document_items=tuple((name, raw[name]) for name in contract.inventory),
        )
    except MotionBundleIntegrityError:
        raise
    except (
        MotionBundleContractError,
        MotionCompileRunError,
        MotionValidationError,
        AttributeError,
        KeyError,
        OverflowError,
        TypeError,
        UnicodeError,
        ValueError,
    ) as exc:
        raise MotionBundleIntegrityError(
            f"Motion bundle integrity verification failed: {exc}"
        ) from exc


def _strict_json(data: bytes, label: str) -> dict[str, Any]:
    try:
        text = data.decode("utf-8")

        def pairs(items):
            result = {}
            for key, value in items:
                if key in result:
                    raise MotionBundleIntegrityError(
                        f"Motion bundle JSON contains a duplicate key: {label}"
                    )
                result[key] = value
            return result

        def nonfinite(_value):
            raise MotionBundleIntegrityError(
                f"Motion bundle JSON contains a non-finite number: {label}"
            )

        value = json.loads(
            text, object_pairs_hook=pairs, parse_constant=nonfinite
        )
    except MotionBundleIntegrityError:
        raise
    except (UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise MotionBundleIntegrityError(
            f"Motion bundle JSON is invalid: {label}"
        ) from exc
    if not isinstance(value, dict):
        raise MotionBundleIntegrityError(
            f"Motion bundle JSON must be an object: {label}"
        )
    return value


def _exact_items(items: Any) -> tuple[dict[str, bytes], str]:
    if type(items) is not tuple:
        raise MotionBundleIntegrityError("Motion bundle inventory is invalid")
    names = tuple(
        item[0] for item in items if type(item) is tuple and len(item) == 2
    )
    try:
        profile = profile_for_ordered_names(names)
    except MotionBundleInventoryError as exc:
        raise MotionBundleIntegrityError("Motion bundle inventory is invalid")
    limits = profile.limit_by_name
    result: dict[str, bytes] = {}
    for item in items:
        if type(item) is not tuple or len(item) != 2:
            raise MotionBundleIntegrityError("Motion bundle inventory is invalid")
        name, data = item
        if type(name) is not str or name in result or type(data) is not bytes:
            raise MotionBundleIntegrityError("Motion bundle inventory is invalid")
        if name not in limits or len(data) > limits[name]:
            raise MotionBundleIntegrityError("Motion bundle byte budget is exceeded")
        result[name] = data
    return result, profile.source_kind


def _rebuild_builtin(motion, stored_run):
    require_motion_ir(motion)
    require_motion_compile_run(stored_run, motion_ir=motion)
    clip_id = _clip_id(motion, stored_run)
    rebuilt_run = build_builtin_motion_compile_run(clip_id, motion)
    contract = build_motion_bundle_contract(motion, rebuilt_run.document)
    return clip_id, contract, rebuilt_run.sha256


def _rebuild_bvh(raw_bvh, bvh_map, motion, stored_run):
    require_motion_ir(motion)
    contract = build_motion_bundle_contract(
        motion, stored_run, raw_bvh=raw_bvh, bvh_map=bvh_map,
    )
    # The contract already recompiles raw BVH + map and byte-compares the run.
    # Returning its bound run SHA avoids repeating the potentially large FK pass.
    return contract.clip_id, contract, contract.run_sha256


def _rebuild_kimodo(raw_npz, source, mapping, motion, stored_run):
    require_motion_ir(motion)
    contract = build_motion_bundle_contract(
        motion, stored_run,
        raw_npz=raw_npz, kimodo_source=source, kimodo_map=mapping,
    )
    # As with BVH, the source-specific contract has already recompiled the
    # archive and byte-compared the run; avoid a second matrix-FK pass here.
    return contract.clip_id, contract, contract.run_sha256


def _clip_id(motion: Mapping[str, Any], run: Mapping[str, Any]) -> str:
    clip_id = motion.get("clip_id")
    source = run.get("source")
    if (
        not isinstance(clip_id, str)
        or not isinstance(source, Mapping)
        or source.get("builtin_id") != clip_id
    ):
        raise MotionBundleIntegrityError(
            "Motion clip id and compile-run built-in id are cross-bound incorrectly"
        )
    return clip_id


def _require_address(path: Path, contract: Any) -> None:
    if (
        path.name != contract.bundle_sha256
        or path.parent.name != contract.clip_sha256
        or path.parent.parent.name != "motions"
    ):
        raise MotionBundleIntegrityError(
            "Motion bundle content-address path is invalid"
        )
