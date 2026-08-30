"""Bounded exact-input reuse for stored bilateral split validation."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
import hashlib
from importlib import import_module
import json
import os
from pathlib import Path
import re
from threading import Event, RLock
from types import FunctionType
from typing import Any

from .idle_behavior_review_byte_seal import (
    IdleBehaviorReviewReplayCacheError,
    seal_exact_directories,
    trusted_root,
)
from .resolved_project import canonical_sha256


MIN_CAPACITY = 32
MAX_CAPACITY = 256
DEFAULT_CAPACITY = 128
_SHA = re.compile(r"^[0-9a-f]{64}$")
_PROJECT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_RUNTIME_MODULES = (
    "alpha_bilateral_split",
    "alpha_geometry",
    "bilateral_component_assignment",
    "candidate_decisions",
    "contracts",
    "manifest_artifacts",
    "manifest_bundle",
    "png_rgba",
    "resolved_project",
    "split_binding_target",
    "split_component_policy",
    "split_decision_binder",
    "split_decision_persistence",
    "split_derivation_contract",
    "split_preview_contract",
    "split_preview_reader",
    "split_spec_resolution",
)


class SplitDecisionValidationCacheError(RuntimeError):
    """Raised when exact cache inputs or compiler values are unsafe."""


@dataclass(frozen=True, slots=True)
class SplitDecisionValidationCacheKey:
    """All mutable inputs observed by stored split revalidation."""

    state_root: str
    project_id: str
    decision_context_sha256: str
    evidence_sha256: str
    algorithm_runtime_sha256: str


@dataclass(frozen=True, slots=True)
class _FrozenResult:
    encoded: str

    @classmethod
    def freeze(cls, value: dict[str, dict[str, Any]]) -> _FrozenResult:
        if type(value) is not dict:
            raise SplitDecisionValidationCacheError(
                "Stored split validator returned an unsupported value"
            )
        try:
            encoded = json.dumps(
                value, ensure_ascii=False, allow_nan=False,
                sort_keys=True, separators=(",", ":"),
            )
        except (OverflowError, TypeError, UnicodeError, ValueError) as exc:
            raise SplitDecisionValidationCacheError(
                "Stored split validator returned non-JSON data"
            ) from exc
        return cls(encoded)

    def thaw(self) -> dict[str, dict[str, Any]]:
        return json.loads(self.encoded)


@dataclass(slots=True)
class _Flight:
    done: Event = field(default_factory=Event)
    value: _FrozenResult | None = None
    error: BaseException | None = None


class SplitDecisionValidationCache:
    """Bounded single-flight LRU; failed validations never become resident."""

    def __init__(self, *, capacity: int = DEFAULT_CAPACITY) -> None:
        if type(capacity) is not int or not MIN_CAPACITY <= capacity <= MAX_CAPACITY:
            raise SplitDecisionValidationCacheError(
                "Stored split cache capacity is invalid"
            )
        self._capacity = capacity
        self._values: OrderedDict[
            SplitDecisionValidationCacheKey, _FrozenResult
        ] = OrderedDict()
        self._flights: dict[
            tuple[int, SplitDecisionValidationCacheKey], _Flight
        ] = {}
        self._generation = 0
        self._lock = RLock()

    def get_or_validate(
        self,
        key: SplitDecisionValidationCacheKey,
        validator: Callable[[], dict[str, dict[str, Any]]],
    ) -> dict[str, dict[str, Any]]:
        if type(key) is not SplitDecisionValidationCacheKey \
                or not callable(validator):
            raise SplitDecisionValidationCacheError(
                "Stored split cache request is invalid"
            )
        with self._lock:
            generation = self._generation
            cached = self._values.pop(key, None)
            if cached is not None:
                self._values[key] = cached
                return cached.thaw()
            flight_key = (generation, key)
            flight = self._flights.get(flight_key)
            leader = flight is None
            if flight is None:
                flight = _Flight()
                self._flights[flight_key] = flight
        if not leader:
            flight.done.wait()
            if flight.error is not None:
                raise flight.error
            if flight.value is None:
                raise SplitDecisionValidationCacheError(
                    "Stored split single-flight completed without a value"
                )
            return flight.value.thaw()
        try:
            frozen = _FrozenResult.freeze(validator())
            with self._lock:
                if generation == self._generation:
                    self._values[key] = frozen
                    self._values.move_to_end(key)
                    while len(self._values) > self._capacity:
                        self._values.popitem(last=False)
                self._flights.pop(flight_key, None)
                flight.value = frozen
                flight.done.set()
            return frozen.thaw()
        except BaseException as exc:
            with self._lock:
                self._flights.pop(flight_key, None)
                flight.error = exc
                flight.done.set()
            raise

    def clear(self) -> None:
        with self._lock:
            self._generation += 1
            self._values.clear()


def split_decision_validation_cache_key(
    state_root: Path,
    project_id: str,
    decisions: Mapping[str, Any],
    resolved: Mapping[str, Any],
    source_paths: Mapping[str, Path],
) -> SplitDecisionValidationCacheKey:
    """Seal every decision, source raster, preview, and manifest bundle."""

    try:
        root = trusted_root(Path(state_root))
        if not isinstance(project_id, str) or not _PROJECT.fullmatch(project_id):
            raise SplitDecisionValidationCacheError(
                "Stored split cache project id is invalid"
            )
        if not isinstance(decisions, Mapping) \
                or not isinstance(resolved, Mapping) \
                or not isinstance(source_paths, Mapping):
            raise SplitDecisionValidationCacheError(
                "Stored split cache context is invalid"
            )
        evidence: list[dict[str, Any]] = []
        for layer_id in sorted(decisions, key=str):
            row = decisions[layer_id]
            if not isinstance(layer_id, str) or not _PROJECT.fullmatch(layer_id) \
                    or not isinstance(row, Mapping):
                raise SplitDecisionValidationCacheError(
                    "Stored split cache decision is invalid"
                )
            preview_sha = _digest(row.get("split_artifact_sha256"), "preview")
            analysis = row.get("analysis")
            if not isinstance(analysis, Mapping):
                raise SplitDecisionValidationCacheError(
                    "Stored split cache analysis is invalid"
                )
            manifest_sha = _digest(
                analysis.get("layer_manifest_sha256"), "manifest"
            )
            source = source_paths.get(layer_id)
            if source is None:
                raise SplitDecisionValidationCacheError(
                    "Stored split cache source raster is unavailable"
                )
            preview = root / "analysis" / project_id / "split-previews" \
                / f"{preview_sha}.json"
            manifest = root / "builds" / project_id / "layer-manifests" \
                / manifest_sha
            evidence.append({
                "layer_id": layer_id,
                "source": _seal_file(Path(source)),
                "preview": _seal_file(preview, root=root),
                "manifest": seal_exact_directories(root, (manifest,)),
            })
        context_sha = canonical_sha256({
            "format": "autospine-stored-split-validation-context",
            "format_version": 1,
            "decisions": decisions,
            "resolved": resolved,
        })
        evidence_sha = canonical_sha256({
            "format": "autospine-stored-split-validation-evidence",
            "format_version": 1,
            "items": evidence,
        })
        return SplitDecisionValidationCacheKey(
            str(root), project_id, context_sha, evidence_sha,
            _runtime_sha256(),
        )
    except SplitDecisionValidationCacheError:
        raise
    except (
        IdleBehaviorReviewReplayCacheError, OSError, TypeError, ValueError,
    ) as exc:
        raise SplitDecisionValidationCacheError(
            "Stored split cache inputs could not be sealed"
        ) from exc


def _seal_file(path: Path, *, root: Path | None = None) -> dict[str, Any]:
    try:
        lexical = Path(os.path.abspath(os.fspath(path)))
        if lexical.is_symlink():
            raise OSError("link-like input")
        resolved = lexical.resolve(strict=True)
        if root is not None:
            resolved.relative_to(root)
        before = resolved.stat()
        if not resolved.is_file():
            raise OSError("not a regular file")
        with resolved.open("rb") as handle:
            opened = os.fstat(handle.fileno())
            digest = hashlib.file_digest(handle, "sha256").hexdigest()
            finished = os.fstat(handle.fileno())
        after = resolved.stat()
        if _identity(before) != _identity(opened) \
                or _identity(before) != _identity(finished) \
                or _identity(before) != _identity(after):
            raise OSError("input changed while hashing")
        return {"path": str(resolved), "size": before.st_size, "sha256": digest}
    except (OSError, RuntimeError, ValueError) as exc:
        raise SplitDecisionValidationCacheError(
            "Stored split cache file could not be sealed"
        ) from exc


def _runtime_sha256() -> str:
    rows = []
    for short_name in _RUNTIME_MODULES:
        module = import_module(f"autospine_workbench.{short_name}")
        source = Path(str(module.__file__ or ""))
        symbols = [
            _callable_identity(name, value, module.__name__)
            for name, value in sorted(vars(module).items())
            if not name.startswith("__") and callable(value)
        ]
        rows.append({
            "module": module.__name__,
            "source": _seal_file(source),
            "symbols": symbols,
        })
    return canonical_sha256({
        "format": "autospine-stored-split-validator-runtime",
        "format_version": 1,
        "modules": rows,
    })


def _callable_identity(name: str, value: Any, owner: str) -> dict[str, Any]:
    row: dict[str, Any] = {
        "name": name,
        "object_id": id(value),
        "module": str(getattr(value, "__module__", "")),
        "qualname": str(getattr(value, "__qualname__", "")),
    }
    code = getattr(value, "__code__", None)
    if code is not None:
        row["code_object_id"] = id(code)
    if isinstance(value, type) and value.__module__ == owner:
        methods = []
        for method_name, raw in sorted(vars(value).items()):
            target = (
                raw.__func__
                if isinstance(raw, (classmethod, staticmethod))
                else raw
            )
            if isinstance(target, FunctionType):
                methods.append({
                    "name": method_name,
                    "object_id": id(target),
                    "code_object_id": id(target.__code__),
                })
        row["methods"] = methods
    return row


def _identity(value) -> tuple[int, ...]:
    return (
        value.st_mode, value.st_size, value.st_mtime_ns,
        getattr(value, "st_dev", 0), getattr(value, "st_ino", 0),
    )


def _digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        raise SplitDecisionValidationCacheError(
            f"Stored split cache {label} SHA-256 is invalid"
        )
    return value


_PROCESS_CACHE = SplitDecisionValidationCache()


def process_split_decision_validation_cache() -> SplitDecisionValidationCache:
    return _PROCESS_CACHE


def clear_split_decision_validation_cache() -> None:
    _PROCESS_CACHE.clear()
