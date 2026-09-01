"""Bounded process-local reuse for exact current Layer Manifest builds."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
import hashlib
from importlib import import_module
from pathlib import Path
import re
from threading import Event, RLock
from types import FunctionType
from typing import Any

from .resolved_project import canonical_sha256


MIN_CAPACITY = 2
MAX_CAPACITY = 32
DEFAULT_CAPACITY = 8
_SHA = re.compile(r"^[0-9a-f]{64}$")
_ALGORITHM_MODULES = (
    "alpha_bilateral_split",
    "alpha_geometry",
    "bilateral_component_assignment",
    "layer_manifest",
    "layer_split_materializer",
    "manifest_artifacts",
    "png_rgba",
    "polyline_distance",
    "resolved_snapshot_validation",
    "rig_roles",
    "split_bundle_validation",
    "split_component_policy",
    "split_derivation_contract",
    "split_materialization_review",
    "split_spec_resolution",
)


class CurrentProjectChainCacheError(RuntimeError):
    """Raised when a cache identity or compiler result is unsafe."""


@dataclass(frozen=True, slots=True)
class CurrentProjectChainCacheKey:
    """Exact inputs for one deterministic current Layer Manifest."""

    project_id: str
    resolved_project_sha256: str
    source_raster_set_sha256: str
    algorithm_runtime_sha256: str

    @property
    def input_identity_sha256(self) -> str:
        return canonical_sha256({
            "format": "autospine-current-chain-input",
            "format_version": 1,
            "project_id": self.project_id,
            "resolved_project_sha256": self.resolved_project_sha256,
            "source_raster_set_sha256": self.source_raster_set_sha256,
            "algorithm_runtime_sha256": self.algorithm_runtime_sha256,
        })


@dataclass(slots=True)
class _Flight:
    done: Event = field(default_factory=Event)
    value: str | None = None
    error: BaseException | None = None


class CurrentProjectChainCache:
    """Per-key single-flight LRU; failures are never resident values."""

    def __init__(self, *, capacity: int = DEFAULT_CAPACITY) -> None:
        if type(capacity) is not int or not MIN_CAPACITY <= capacity <= MAX_CAPACITY:
            raise CurrentProjectChainCacheError(
                "Current project chain cache capacity is invalid"
            )
        self._capacity = capacity
        self._values: OrderedDict[CurrentProjectChainCacheKey, str] = OrderedDict()
        self._flights: dict[CurrentProjectChainCacheKey, _Flight] = {}
        self._lock = RLock()

    def get_or_compile(
        self,
        key: CurrentProjectChainCacheKey,
        compiler: Callable[[], str],
    ) -> str:
        """Return one exact manifest SHA; only one compiler runs per key."""

        if type(key) is not CurrentProjectChainCacheKey or not callable(compiler):
            raise CurrentProjectChainCacheError(
                "Current project chain cache request is invalid"
            )
        with self._lock:
            cached = self._values.pop(key, None)
            if cached is not None:
                self._values[key] = cached
                return cached
            flight = self._flights.get(key)
            leader = flight is None
            if flight is None:
                flight = _Flight()
                self._flights[key] = flight
        if not leader:
            flight.done.wait()
            if flight.error is not None:
                raise flight.error
            return _digest(flight.value, "manifest")
        try:
            value = _digest(compiler(), "manifest")
            with self._lock:
                self._values[key] = value
                self._values.move_to_end(key)
                while len(self._values) > self._capacity:
                    self._values.popitem(last=False)
                self._flights.pop(key, None)
                flight.value = value
                flight.done.set()
            return value
        except BaseException as exc:
            with self._lock:
                self._flights.pop(key, None)
                flight.error = exc
                flight.done.set()
            raise

    def clear(self) -> None:
        """Discard resident values without interrupting active compilers."""

        with self._lock:
            self._values.clear()


_CACHE = CurrentProjectChainCache()


def current_project_chain_cache_key(
    project_id: str,
    resolved_project_sha256: str,
    assets: Mapping[str, Path],
) -> CurrentProjectChainCacheKey:
    """Hash every source raster byte and the live manifest algorithm graph."""

    if not isinstance(project_id, str) or not project_id:
        raise CurrentProjectChainCacheError("Current project id is invalid")
    resolved_sha = _digest(resolved_project_sha256, "resolved project")
    if not isinstance(assets, Mapping) or not assets:
        raise CurrentProjectChainCacheError("Current source raster set is invalid")
    rows = []
    for layer_id in sorted(assets):
        if not isinstance(layer_id, str) or not layer_id:
            raise CurrentProjectChainCacheError("Current layer id is invalid")
        path = assets[layer_id]
        if not isinstance(path, Path):
            path = Path(path)
        rows.append({"layer_id": layer_id, "sha256": _sha256_path(path)})
    source_sha = canonical_sha256({
        "format": "autospine-current-source-rasters",
        "format_version": 1,
        "rasters": rows,
    })
    return CurrentProjectChainCacheKey(
        project_id,
        resolved_sha,
        source_sha,
        current_manifest_algorithm_runtime_sha256(),
    )


def get_cached_current_project_manifest(
    key: CurrentProjectChainCacheKey,
    compiler: Callable[[], str],
) -> str:
    return _CACHE.get_or_compile(key, compiler)


def clear_current_project_chain_cache() -> None:
    _CACHE.clear()


def current_manifest_algorithm_runtime_sha256() -> str:
    """Bind source plus ordinary live callable rebinding, path-independently."""

    modules = []
    for short_name in _ALGORITHM_MODULES:
        module = import_module(f"autospine_workbench.{short_name}")
        path = Path(str(module.__file__ or "")).resolve(strict=True)
        symbols = []
        for name, value in sorted(vars(module).items()):
            if name.startswith("__"):
                continue
            if callable(value):
                symbols.append(_callable_identity(name, value, module.__name__))
            elif name.upper() == name:
                normalized = _simple_value(value)
                if normalized is not None:
                    symbols.append({"name": name, "constant": normalized})
        modules.append({
            "module": module.__name__,
            "source_sha256": _sha256_path(path),
            "symbols": symbols,
        })
    return canonical_sha256({
        "format": "autospine-current-manifest-algorithm-runtime",
        "format_version": 1,
        "modules": modules,
    })


def _callable_identity(name: str, value: Any, owner: str) -> dict[str, Any]:
    row: dict[str, Any] = {
        "name": name,
        "owner": owner,
        "type": f"{type(value).__module__}.{type(value).__qualname__}",
        "module": str(getattr(value, "__module__", "")),
        "qualname": str(getattr(value, "__qualname__", "")),
    }
    source = _source_locator(value, owner)
    if source is not None:
        row["source"] = source
    if isinstance(value, type) and value.__module__ == owner:
        methods = []
        for method_name, raw in sorted(vars(value).items()):
            target = (
                raw.__func__
                if isinstance(raw, (classmethod, staticmethod))
                else raw
            )
            if isinstance(target, FunctionType) \
                    and target.__module__ == owner:
                methods.append(_callable_identity(method_name, target, owner))
        row["methods"] = methods
    return row


def _source_locator(value: Any, owner: str) -> dict[str, Any] | None:
    """Describe live code without binding the digest to CPython bytecode."""

    code = getattr(value, "__code__", None)
    if code is None:
        return None
    try:
        module = import_module(owner)
        owner_path = Path(str(module.__file__ or "")).resolve(strict=True)
        code_path = Path(code.co_filename).resolve(strict=True)
    except (OSError, RuntimeError, TypeError, ValueError):
        return {"kind": "external"}
    if owner_path != code_path:
        return {"kind": "external"}
    return {"kind": "owner", "first_line": code.co_firstlineno}


def _simple_value(value: Any) -> Any | None:
    if value is None or type(value) in {bool, int, float, str}:
        return value
    if isinstance(value, re.Pattern):
        return {"pattern": value.pattern, "flags": value.flags}
    if isinstance(value, (tuple, frozenset)) and len(value) <= 128:
        rows = [_simple_value(item) for item in value]
        if all(item is not None for item in rows):
            return sorted(rows, key=repr) if isinstance(value, frozenset) else rows
    return None


def _sha256_path(path: Path) -> str:
    try:
        if path.is_symlink():
            raise OSError("link-like input")
        resolved = path.resolve(strict=True)
        if not resolved.is_file():
            raise OSError("input is not a regular file")
        with resolved.open("rb") as handle:
            return hashlib.file_digest(handle, "sha256").hexdigest()
    except OSError as exc:
        raise CurrentProjectChainCacheError(
            "Current project chain input could not be hashed"
        ) from exc


def _digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        raise CurrentProjectChainCacheError(f"Current {label} SHA-256 is invalid")
    return value
