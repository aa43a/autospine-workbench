"""Bounded single-flight in-process cache for exact Preview v2 values."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from threading import Event, RLock

from .capture_framing_candidate import CaptureFramingCandidate
from .idle_behavior_candidates import IdleBehaviorCandidates
from .idle_behavior_review_address import IdleBehaviorReviewAddress
from .p10_preview_v2_result import P10PreviewV2CommandResult


DEFAULT_CAPACITY = 4
DEFAULT_BYTE_CAPACITY = 64 * 1024 * 1024


class P10PreviewV2CacheError(RuntimeError):
    """Raised when Preview v2 acceleration cannot preserve exact identity."""


@dataclass(frozen=True, slots=True)
class P10PreviewV2CacheLocator:
    state_root: str
    workspace_root: str
    package_id: str
    compiler_inventory_sha256: str


@dataclass(frozen=True, slots=True)
class P10PreviewV2CacheKey:
    locator: P10PreviewV2CacheLocator
    inventory_sha256: str
    p10_candidate_sha256: str
    p10_decision_sha256: str
    p10_revision: int
    framing_candidate_sha256: str
    framing_decision_sha256: str
    framing_revision: int


@dataclass(frozen=True, slots=True)
class P10PreviewV2CacheRecord:
    key: P10PreviewV2CacheKey
    address: IdleBehaviorReviewAddress
    candidates: IdleBehaviorCandidates
    framing_candidate: CaptureFramingCandidate
    result: P10PreviewV2CommandResult

    @property
    def cache_weight_bytes(self) -> int:
        return (
            self.result.cache_weight_bytes
            + len(self.candidates.canonical_bytes)
            + len(self.framing_candidate.canonical_bytes)
        )


@dataclass(slots=True)
class _Flight:
    done: Event = field(default_factory=Event)
    value: P10PreviewV2CacheRecord | None = None
    error: BaseException | None = None


class P10PreviewV2Cache:
    """LRU cache whose hits revalidate mutable heads through one flight."""

    def __init__(
        self, *, capacity: int = DEFAULT_CAPACITY,
        byte_capacity: int = DEFAULT_BYTE_CAPACITY,
    ) -> None:
        if type(capacity) is not int or not 1 <= capacity <= 8:
            raise P10PreviewV2CacheError("Preview v2 cache capacity is invalid")
        if type(byte_capacity) is not int \
                or not 1024 <= byte_capacity <= 128 * 1024 * 1024:
            raise P10PreviewV2CacheError("Preview v2 byte capacity is invalid")
        self._capacity = capacity
        self._byte_capacity = byte_capacity
        self._resident_bytes = 0
        self._values: OrderedDict[
            P10PreviewV2CacheKey, P10PreviewV2CacheRecord
        ] = OrderedDict()
        self._flights: dict[P10PreviewV2CacheLocator, _Flight] = {}
        self._lock = RLock()

    def get_or_compile(
        self,
        locator: P10PreviewV2CacheLocator,
        validator: Callable[[P10PreviewV2CacheRecord], bool],
        compiler: Callable[[], P10PreviewV2CacheRecord],
    ) -> P10PreviewV2CacheRecord:
        if type(locator) is not P10PreviewV2CacheLocator \
                or not callable(validator) or not callable(compiler):
            raise P10PreviewV2CacheError("Preview v2 cache request is invalid")
        with self._lock:
            flight = self._flights.get(locator)
            leader = flight is None
            if flight is None:
                flight = _Flight()
                self._flights[locator] = flight
            cached = self._latest(locator) if leader else None
        if not leader:
            flight.done.wait()
            if flight.error is not None:
                raise flight.error
            return _record(flight.value)
        try:
            value = self._load(locator, cached, validator, compiler)
            with self._lock:
                self._flights.pop(locator, None)
                flight.value = value
                flight.done.set()
            return value
        except BaseException as exc:
            with self._lock:
                self._flights.pop(locator, None)
                flight.error = exc
                flight.done.set()
            raise

    def clear(self) -> None:
        with self._lock:
            self._values.clear()
            self._resident_bytes = 0

    def _latest(self, locator):
        return next((value for key, value in reversed(self._values.items())
                     if key.locator == locator), None)

    def _load(self, locator, cached, validator, compiler):
        if cached is not None:
            if validator(cached) is True:
                with self._lock:
                    if self._values.get(cached.key) is cached:
                        self._values.move_to_end(cached.key)
                return cached
            self._discard(cached)
        value = _record(compiler())
        if value.key.locator != locator:
            raise P10PreviewV2CacheError("Compiled Preview v2 locator changed")
        self._store(value)
        return value

    def _discard(self, value):
        with self._lock:
            if self._values.pop(value.key, None) is not None:
                self._resident_bytes -= value.cache_weight_bytes

    def _store(self, value):
        weight = value.cache_weight_bytes
        if type(weight) is not int or weight < 0:
            raise P10PreviewV2CacheError("Preview v2 cache weight is invalid")
        if weight > self._byte_capacity:
            return
        with self._lock:
            previous = self._values.pop(value.key, None)
            if previous is not None:
                self._resident_bytes -= previous.cache_weight_bytes
            while self._values and (
                len(self._values) >= self._capacity
                or self._resident_bytes + weight > self._byte_capacity
            ):
                _key, evicted = self._values.popitem(last=False)
                self._resident_bytes -= evicted.cache_weight_bytes
            self._values[value.key] = value
            self._resident_bytes += weight


def _record(value):
    if type(value) is not P10PreviewV2CacheRecord:
        raise P10PreviewV2CacheError("Preview v2 cache value is invalid")
    return value


_PROCESS_CACHE = P10PreviewV2Cache()


def process_p10_preview_v2_cache() -> P10PreviewV2Cache:
    return _PROCESS_CACHE


def clear_p10_preview_v2_cache() -> None:
    _PROCESS_CACHE.clear()


__all__ = [
    "P10PreviewV2Cache", "P10PreviewV2CacheError",
    "P10PreviewV2CacheKey", "P10PreviewV2CacheLocator",
    "P10PreviewV2CacheRecord", "clear_p10_preview_v2_cache",
    "process_p10_preview_v2_cache",
]
