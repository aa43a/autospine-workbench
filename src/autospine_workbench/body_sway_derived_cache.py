"""Bounded single-flight cache for exact P10.2 derived diagnostics."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
import re
from threading import Event, RLock

from .body_sway_canvas_adjustment_profile import (
    FORMAT as CANVAS_FORMAT,
    FORMAT_VERSION as CANVAS_FORMAT_VERSION,
    body_sway_canvas_adjustment_analyzer_profile,
)
from .body_sway_derived_value import BodySwayDerivedResult
from .body_sway_probe_profile import body_sway_probe_profile
from .body_sway_probe_validation import (
    FORMAT as PROBE_FORMAT,
    FORMAT_VERSION as PROBE_FORMAT_VERSION,
)
from .dynamic_viewport_fit import (
    FORMAT as VIEWPORT_FORMAT,
    FORMAT_VERSION as VIEWPORT_FORMAT_VERSION,
    dynamic_viewport_fit_profile,
)
from .idle_behavior_review_address import IdleBehaviorReviewAddress
from .idle_behavior_review_head import IdleBehaviorReviewHead
from .resolved_project import canonical_sha256
from .region_rebind_profile import (
    FORMAT as REBIND_FORMAT,
    FORMAT_VERSION as REBIND_FORMAT_VERSION,
    region_rebind_analyzer_profile,
)


MIN_CAPACITY = 4
MAX_CAPACITY = 8
MIN_BYTE_CAPACITY = 16 * 1024 * 1024
MAX_BYTE_CAPACITY = 32 * 1024 * 1024
DEFAULT_CAPACITY = 6
DEFAULT_BYTE_CAPACITY = 24 * 1024 * 1024
_SHA = re.compile(r"^[0-9a-f]{64}$")


class BodySwayDerivedCacheError(RuntimeError):
    """Raised when a derived cache key or value is unsafe."""


@dataclass(frozen=True, slots=True)
class BodySwayDerivedCacheKey:
    """Exact immutable identity for one current-head compiler result."""

    state_root: str
    address: IdleBehaviorReviewAddress
    candidate_sha256: str
    review_revision: int
    decision_sha256: str
    probe_profile_sha256: str
    canvas_profile_sha256: str
    viewport_profile_sha256: str
    rebind_profile_sha256: str


@dataclass(slots=True)
class _Flight:
    done: Event = field(default_factory=Event)
    value: BodySwayDerivedResult | None = None
    error: BaseException | None = None


class BodySwayDerivedCache:
    """Per-key single-flight LRU with both entry and byte limits."""

    def __init__(
        self, *, capacity: int = DEFAULT_CAPACITY,
        byte_capacity: int = DEFAULT_BYTE_CAPACITY,
    ) -> None:
        if type(capacity) is not int \
                or not MIN_CAPACITY <= capacity <= MAX_CAPACITY:
            raise BodySwayDerivedCacheError(
                "P10.2 derived cache capacity is invalid"
            )
        if type(byte_capacity) is not int \
                or not MIN_BYTE_CAPACITY <= byte_capacity \
                <= MAX_BYTE_CAPACITY:
            raise BodySwayDerivedCacheError(
                "P10.2 derived cache byte capacity is invalid"
            )
        self._capacity = capacity
        self._byte_capacity = byte_capacity
        self._values: OrderedDict[
            BodySwayDerivedCacheKey, BodySwayDerivedResult
        ] = OrderedDict()
        self._resident_bytes = 0
        self._flights: dict[BodySwayDerivedCacheKey, _Flight] = {}
        self._lock = RLock()

    def get_or_compile(
        self, key: BodySwayDerivedCacheKey,
        compiler: Callable[[], BodySwayDerivedResult],
    ) -> BodySwayDerivedResult:
        """Return one immutable result; only one compiler runs per key."""

        if type(key) is not BodySwayDerivedCacheKey or not callable(compiler):
            raise BodySwayDerivedCacheError(
                "P10.2 derived cache request is invalid"
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
            if flight.value is None:
                raise BodySwayDerivedCacheError(
                    "P10.2 derived single-flight completed without a value"
                )
            return flight.value
        try:
            value = compiler()
            if type(value) is not BodySwayDerivedResult:
                raise BodySwayDerivedCacheError(
                    "P10.2 derived compiler returned an unsupported value"
                )
            self._finish_success(key, flight, value)
            return value
        except BaseException as exc:
            with self._lock:
                self._flights.pop(key, None)
                flight.error = exc
                flight.done.set()
            raise

    def clear(self) -> None:
        """Clear resident values without interrupting active compilers."""

        with self._lock:
            self._values.clear()
            self._resident_bytes = 0

    def _finish_success(self, key, flight, value) -> None:
        weight = value.cache_weight_bytes
        if type(weight) is not int or weight < 0:
            raise BodySwayDerivedCacheError(
                "P10.2 derived cache weight is invalid"
            )
        with self._lock:
            if weight <= self._byte_capacity:
                while self._values and (
                    len(self._values) >= self._capacity
                    or self._resident_bytes + weight > self._byte_capacity
                ):
                    _old_key, old = self._values.popitem(last=False)
                    self._resident_bytes -= old.cache_weight_bytes
                self._values[key] = value
                self._resident_bytes += weight
            self._flights.pop(key, None)
            flight.value = value
            flight.done.set()


def body_sway_derived_cache_key(
    state_root: Path,
    address: IdleBehaviorReviewAddress,
    candidate_sha256: str,
    current_head: IdleBehaviorReviewHead,
) -> BodySwayDerivedCacheKey:
    """Bind derived reuse to the root, exact address, head, and profiles."""

    try:
        root = Path(state_root).expanduser().resolve(strict=True)
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise BodySwayDerivedCacheError(
            "P10.2 derived cache state root is invalid"
        ) from exc
    exact_head = type(current_head) is IdleBehaviorReviewHead
    decision_sha = current_head.decision_sha256 if exact_head else None
    revision = current_head.current_revision if exact_head else None
    if not root.is_dir() \
            or type(address) is not IdleBehaviorReviewAddress \
            or not isinstance(candidate_sha256, str) \
            or not _SHA.fullmatch(candidate_sha256) \
            or type(revision) is not int or revision < 1 \
            or not isinstance(decision_sha, str) \
            or not _SHA.fullmatch(decision_sha):
        raise BodySwayDerivedCacheError(
            "P10.2 derived cache identity is invalid"
        )
    return BodySwayDerivedCacheKey(
        str(root), address, candidate_sha256,
        revision, decision_sha,
        _profile_sha(
            "autospine-body-sway-probe-cache-profile/v1",
            PROBE_FORMAT, PROBE_FORMAT_VERSION, body_sway_probe_profile(),
        ),
        _profile_sha(
            "autospine-body-sway-canvas-cache-profile/v1",
            CANVAS_FORMAT, CANVAS_FORMAT_VERSION,
            body_sway_canvas_adjustment_analyzer_profile(),
        ),
        _profile_sha(
            "autospine-dynamic-viewport-cache-profile/v1",
            VIEWPORT_FORMAT, VIEWPORT_FORMAT_VERSION,
            dynamic_viewport_fit_profile(),
        ),
        _profile_sha(
            "autospine-region-rebind-cache-profile/v1",
            REBIND_FORMAT, REBIND_FORMAT_VERSION,
            region_rebind_analyzer_profile(),
        ),
    )


def _profile_sha(domain, format_name, format_version, profile) -> str:
    return canonical_sha256({
        "domain": domain, "format": format_name,
        "format_version": format_version, "profile": profile,
    })


_PROCESS_CACHE = BodySwayDerivedCache()


def process_body_sway_derived_cache() -> BodySwayDerivedCache:
    """Return the process-local cache shared by detail and draft routes."""

    return _PROCESS_CACHE


def clear_body_sway_derived_cache() -> None:
    """Clear process-local derived values; primarily for test isolation."""

    _PROCESS_CACHE.clear()
