"""Byte-sealed in-process reuse for immutable P10 exact replay chains."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
import re
from threading import Event, RLock

from .idle_behavior_review_byte_seal import (
    IdleBehaviorReviewReplayCacheError,
    seal_exact_directories,
    trusted_directory,
    trusted_root,
)
from .reviewed_motion_bundle_reader import (
    VerifiedReviewedMotionBundleChain,
)
from .safe_input_files import (
    SafeInputFileError,
    read_real_file,
    strict_json_object,
)


_MAX_ENTRIES = 32
_MAX_DISCOVERY_JSON_BYTES = 32 * 1024 * 1024
_SHA = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class _Entry:
    paths: tuple[Path, ...]
    seal: str
    chain: VerifiedReviewedMotionBundleChain


@dataclass(slots=True)
class _Flight:
    done: Event = field(default_factory=Event)
    value: VerifiedReviewedMotionBundleChain | None = None
    error: BaseException | None = None


_LOCK = RLock()
_CACHE: OrderedDict[tuple[str, str, str, str], _Entry] = OrderedDict()
_FLIGHTS: dict[tuple[int, str, str, str, str], _Flight] = {}
_GENERATION = 0


def load_cached_reviewed_motion_chain(
    state_root: Path,
    project_id: str,
    motion_instance_v2_sha256: str,
    bundle_sha256: str,
    loader: Callable[[], VerifiedReviewedMotionBundleChain],
) -> VerifiedReviewedMotionBundleChain:
    """Singleflight exact replay and reuse only while every byte is unchanged."""

    root = trusted_root(state_root)
    key = (
        str(root), project_id, motion_instance_v2_sha256, bundle_sha256,
    )
    with _LOCK:
        generation = _GENERATION
        flight_key = (generation, *key)
        flight = _FLIGHTS.get(flight_key)
        leader = flight is None
        if flight is None:
            flight = _Flight()
            _FLIGHTS[flight_key] = flight
        entry = _CACHE.get(key) if leader else None
    if not leader:
        flight.done.wait()
        if flight.error is not None:
            raise flight.error
        return _require_chain(flight.value)
    try:
        chain = _load_or_reuse(
            root, key, generation, entry, project_id, motion_instance_v2_sha256,
            bundle_sha256, loader,
        )
        with _LOCK:
            _FLIGHTS.pop(flight_key, None)
            flight.value = chain
            flight.done.set()
        return chain
    except BaseException as exc:
        with _LOCK:
            _FLIGHTS.pop(flight_key, None)
            flight.error = exc
            flight.done.set()
        raise


def _load_or_reuse(
    root: Path,
    key: tuple[str, str, str, str],
    generation: int,
    entry: _Entry | None,
    project_id: str,
    motion_instance_v2_sha256: str,
    bundle_sha256: str,
    loader: Callable[[], VerifiedReviewedMotionBundleChain],
) -> VerifiedReviewedMotionBundleChain:
    if entry is not None:
        try:
            if seal_exact_directories(root, entry.paths) == entry.seal:
                with _LOCK:
                    if _CACHE.get(key) is entry:
                        _CACHE.move_to_end(key)
                return entry.chain
        except IdleBehaviorReviewReplayCacheError:
            pass
        with _LOCK:
            if _CACHE.get(key) is entry:
                _CACHE.pop(key, None)
    try:
        paths_before = _discover_chain_paths(
            root, project_id, motion_instance_v2_sha256, bundle_sha256,
        )
        seal_before = seal_exact_directories(root, paths_before)
    except IdleBehaviorReviewReplayCacheError:
        # Acceleration must not narrow the underlying exact-reader
        # contract. Unsafe evidence will still fail in the exact loader.
        return _require_chain(loader())
    chain = _require_chain(loader())
    paths = _chain_paths(root, chain)
    if paths != paths_before:
        raise IdleBehaviorReviewReplayCacheError(
            "Exact replay inputs changed during verification"
        )
    seal = seal_exact_directories(root, paths)
    if seal != seal_before:
        raise IdleBehaviorReviewReplayCacheError(
            "Exact replay bytes changed during verification"
        )
    with _LOCK:
        if generation == _GENERATION:
            _CACHE[key] = _Entry(paths, seal, chain)
            _CACHE.move_to_end(key)
            while len(_CACHE) > _MAX_ENTRIES:
                _CACHE.popitem(last=False)
    return chain


def clear_idle_behavior_review_replay_cache() -> None:
    """Clear process-local acceleration state; primarily for test isolation."""

    global _GENERATION
    with _LOCK:
        _GENERATION += 1
        _CACHE.clear()


def _require_chain(value) -> VerifiedReviewedMotionBundleChain:
    if type(value) is not VerifiedReviewedMotionBundleChain:
        raise IdleBehaviorReviewReplayCacheError(
            "Exact replay loader returned an unsupported value"
        )
    return value


def _chain_paths(
    root: Path, chain: VerifiedReviewedMotionBundleChain,
) -> tuple[Path, ...]:
    mesh = chain.mesh_bundle
    retarget = chain.retarget_bundle
    reviewed = chain.reviewed_bundle
    mesh_inputs = mesh.run_manifest["inputs"]
    sources = retarget.source_addresses
    paths = (
        root / "builds" / mesh.project_id / "rig-ir"
        / mesh_inputs["base_rig_sha256"] / mesh_inputs["base_bundle_sha256"],
        root / "builds" / mesh.project_id / "layer-manifests"
        / mesh_inputs["layer_manifest_sha256"],
        mesh.path,
        root / "builds" / mesh.project_id / "ik-targets"
        / sources["p4_profile_sha256"] / sources["p4_bundle_sha256"],
        root / "motions" / sources["motion_clip_sha256"]
        / sources["motion_bundle_sha256"],
        retarget.path,
        reviewed.path,
    )
    return tuple(trusted_directory(root, Path(path)) for path in paths)


def _discover_chain_paths(
    root: Path, project: str, instance: str, bundle: str,
) -> tuple[Path, ...]:
    """Read only address manifests needed to seal before expensive replay."""

    p9 = trusted_directory(
        root,
        root / "builds" / project / "reviewed-motion-instances"
        / instance / bundle,
    )
    p9_run = _read_json(p9 / "run-manifest.json", "P9 run manifest")
    inputs = _mapping(p9_run.get("inputs"), "P9 inputs")
    p3_address = _mapping(inputs.get("p3"), "P9 P3 address")
    p5_address = _mapping(inputs.get("p5"), "P9 P5 address")
    p3 = trusted_directory(
        root,
        root / "builds" / project / "mesh-rig-ir"
        / _digest(p3_address.get("rig_sha256"), "P3 rig")
        / _digest(p3_address.get("bundle_sha256"), "P3 bundle"),
    )
    p5 = trusted_directory(
        root,
        root / "builds" / project / "motion-instances"
        / _digest(p5_address.get("instance_sha256"), "P5 instance")
        / _digest(p5_address.get("bundle_sha256"), "P5 bundle"),
    )
    p3_inputs = _mapping(
        _read_json(p3 / "run-manifest.json", "P3 run manifest").get(
            "inputs"
        ),
        "P3 inputs",
    )
    target_source = _mapping(
        _read_json(p5 / "target-profile.json", "P5 target profile").get(
            "source"
        ),
        "P5 target source",
    )
    motion_source = _mapping(
        _read_json(p5 / "instance.json", "P5 instance").get("source"),
        "P5 motion source",
    )
    paths = (
        root / "builds" / project / "rig-ir"
        / _digest(p3_inputs.get("base_rig_sha256"), "P2 rig")
        / _digest(p3_inputs.get("base_bundle_sha256"), "P2 bundle"),
        root / "builds" / project / "layer-manifests"
        / _digest(p3_inputs.get("layer_manifest_sha256"), "manifest"),
        p3,
        root / "builds" / project / "ik-targets"
        / _digest(target_source.get("p4_profile_sha256"), "P4 profile")
        / _digest(target_source.get("p4_bundle_sha256"), "P4 bundle"),
        root / "motions"
        / _digest(motion_source.get("motion_ir_sha256"), "motion clip")
        / _digest(motion_source.get("motion_bundle_sha256"), "motion bundle"),
        p5,
        p9,
    )
    return tuple(trusted_directory(root, Path(path)) for path in paths)


def _read_json(path: Path, label: str) -> dict:
    try:
        return strict_json_object(
            read_real_file(path, _MAX_DISCOVERY_JSON_BYTES, label), label,
        )
    except SafeInputFileError as exc:
        raise IdleBehaviorReviewReplayCacheError(
            "Exact replay address manifest is invalid"
        ) from exc


def _mapping(value, label: str) -> dict:
    if type(value) is not dict:
        raise IdleBehaviorReviewReplayCacheError(f"{label} is invalid")
    return value


def _digest(value, label: str) -> str:
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        raise IdleBehaviorReviewReplayCacheError(f"{label} is invalid")
    return value
