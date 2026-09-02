"""Bounded single-flight cache for exact P10.3c v2 image snapshots."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
import hashlib
from pathlib import Path
from threading import Event, RLock

from .body_sway_runtime_capture_collector import MAX_CAPTURE_TOTAL_BYTES
from .body_sway_runtime_capture_v2_profile import MAX_CAPTURE_ARTIFACTS
from .body_sway_visual_review_address_v2 import ExactVisualReviewAddressV2
from .body_sway_visual_review_application_models_v2 import (
    BodySwayVisualReviewImageV2,
)
from .manifest_artifacts import (
    LayerManifestError, require_safe_token, require_sha256,
)


MAX_IMAGE_CACHE_BYTES = MAX_CAPTURE_TOTAL_BYTES * 2


class P10VisualReviewV2ImageCacheError(RuntimeError):
    pass


class P10VisualReviewV2ImageCacheNotFound(P10VisualReviewV2ImageCacheError):
    pass


@dataclass(frozen=True, slots=True)
class P10VisualReviewV2ImageCacheKey:
    job_id: str
    package_id: str
    address: ExactVisualReviewAddressV2
    candidate_sha256: str

    def __post_init__(self) -> None:
        try:
            require_sha256(self.job_id, "Runtime capture job")
            require_sha256(self.package_id, "Runtime capture package")
            require_sha256(
                self.candidate_sha256, "Visual review v2 candidate",
            )
            if type(self.address) is not ExactVisualReviewAddressV2:
                raise TypeError("address differs")
        except (LayerManifestError, TypeError, ValueError) as exc:
            raise P10VisualReviewV2ImageCacheError(
                "Visual review v2 image cache key is invalid"
            ) from exc


@dataclass(slots=True)
class _Flight:
    done: Event
    value: tuple[BodySwayVisualReviewImageV2, ...] | None = None
    error: BaseException | None = None


class P10VisualReviewV2ImageReplayCache:
    """Retain exact snapshots until LRU eviction/restart, never review state.

    Resident bytes were fully verified at admission. Out-of-contract mutation
    of their content-addressed files requires a server restart; authoritative
    history and submission paths never consume this acceleration cache.
    """

    def __init__(
        self, state_root: Path, *, capacity: int = 2,
        byte_capacity: int = MAX_IMAGE_CACHE_BYTES,
    ) -> None:
        self._state_root = _resolved_root(state_root)
        if type(capacity) is not int or not 1 <= capacity <= 8:
            raise P10VisualReviewV2ImageCacheError(
                "Visual review v2 image cache capacity is invalid"
            )
        if type(byte_capacity) is not int \
                or not 1 <= byte_capacity <= MAX_IMAGE_CACHE_BYTES:
            raise P10VisualReviewV2ImageCacheError(
                "Visual review v2 image cache byte capacity is invalid"
            )
        self._capacity = capacity
        self._byte_capacity = byte_capacity
        self._values: OrderedDict[
            P10VisualReviewV2ImageCacheKey,
            tuple[BodySwayVisualReviewImageV2, ...],
        ] = OrderedDict()
        self._flights: dict[P10VisualReviewV2ImageCacheKey, _Flight] = {}
        self._lock = RLock()

    @property
    def state_root(self) -> Path:
        return self._state_root

    def owns_state_root(self, state_root: Path) -> bool:
        return self._state_root == _resolved_root(state_root)

    def image(
        self, key: P10VisualReviewV2ImageCacheKey, *,
        case_id: str, png_sha256: str,
        loader: Callable[[], tuple[BodySwayVisualReviewImageV2, ...]],
    ) -> BodySwayVisualReviewImageV2:
        if type(key) is not P10VisualReviewV2ImageCacheKey \
                or not callable(loader):
            raise P10VisualReviewV2ImageCacheError(
                "Visual review v2 image cache request is invalid"
            )
        try:
            expected_case = require_safe_token(case_id, "Visual review v2 case")
            expected_png = require_sha256(png_sha256, "Visual review v2 PNG")
        except (LayerManifestError, ValueError) as exc:
            raise P10VisualReviewV2ImageCacheNotFound(
                "Visual review v2 image address is invalid"
            ) from exc
        rows = self._get_or_load(key, loader)
        matches = [row for row in rows if row.case_id == expected_case]
        if len(matches) != 1 or matches[0].png_sha256 != expected_png:
            raise P10VisualReviewV2ImageCacheNotFound(
                "Visual review v2 image identity is cross-wired"
            )
        _verify_image(matches[0], key.candidate_sha256)
        return matches[0]

    def snapshot(
        self, key: P10VisualReviewV2ImageCacheKey, *,
        loader: Callable[[], tuple[BodySwayVisualReviewImageV2, ...]],
    ) -> tuple[BodySwayVisualReviewImageV2, ...]:
        """Admit and return one fully verified immutable image snapshot."""

        if type(key) is not P10VisualReviewV2ImageCacheKey \
                or not callable(loader):
            raise P10VisualReviewV2ImageCacheError(
                "Visual review v2 image cache request is invalid"
            )
        return self._get_or_load(key, loader)

    def _get_or_load(self, key, loader):
        with self._lock:
            cached = self._values.pop(key, None)
            if cached is not None:
                self._values[key] = cached
                return cached
            flight = self._flights.get(key)
            leader = flight is None
            if leader:
                flight = _Flight(Event())
                self._flights[key] = flight
        if not leader:
            flight.done.wait()
            if flight.error is not None:
                raise flight.error
            with self._lock:
                cached = self._values.get(key)
                if cached is None and flight.value is None:
                    raise P10VisualReviewV2ImageCacheError(
                        "Visual review v2 image flight lost its result"
                    )
                if cached is not None:
                    self._values.move_to_end(key)
                    return cached
                return flight.value
        try:
            rows = _verify_snapshot(loader(), key.candidate_sha256)
            flight.value = rows
            self._store(key, rows)
            return rows
        except BaseException as exc:
            flight.error = exc
            raise
        finally:
            with self._lock:
                self._flights.pop(key, None)
                flight.done.set()

    def _store(self, key, rows):
        weight = sum(row.size_bytes for row in rows)
        if weight > self._byte_capacity:
            return
        with self._lock:
            resident = sum(
                sum(row.size_bytes for row in value)
                for value in self._values.values()
            )
            while self._values and (
                len(self._values) >= self._capacity
                or resident + weight > self._byte_capacity
            ):
                _, removed = self._values.popitem(last=False)
                resident -= sum(row.size_bytes for row in removed)
            self._values[key] = rows


def _verify_snapshot(value, candidate_sha256):
    if type(value) is not tuple \
            or not 1 <= len(value) <= MAX_CAPTURE_ARTIFACTS:
        raise P10VisualReviewV2ImageCacheError(
            "Visual review v2 image snapshot is invalid"
        )
    case_ids = set()
    for row in value:
        _verify_image(row, candidate_sha256)
        if row.case_id in case_ids:
            raise P10VisualReviewV2ImageCacheError(
                "Visual review v2 image cases are duplicated"
            )
        case_ids.add(row.case_id)
    return value


def _verify_image(row, candidate_sha256):
    try:
        if type(row) is not BodySwayVisualReviewImageV2:
            raise TypeError("image type differs")
        require_sha256(row.candidate_sha256, "Cached image candidate")
        require_safe_token(row.case_id, "Cached image case")
        require_sha256(row.evidence_sha256, "Cached image evidence")
        require_sha256(row.png_sha256, "Cached image PNG")
    except (LayerManifestError, TypeError, ValueError) as exc:
        raise P10VisualReviewV2ImageCacheError(
            "Visual review v2 cached image identity is invalid"
        ) from exc
    if row.candidate_sha256 != candidate_sha256 \
            or type(row.png_bytes) is not bytes \
            or type(row.size_bytes) is not int \
            or len(row.png_bytes) != row.size_bytes \
            or hashlib.sha256(row.png_bytes).hexdigest() != row.png_sha256 \
            or (row.width, row.height) != (640, 640):
        raise P10VisualReviewV2ImageCacheError(
            "Visual review v2 cached image differs from evidence"
        )


def _resolved_root(value):
    try:
        return Path(value).expanduser().resolve()
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise P10VisualReviewV2ImageCacheError(
            "Visual review v2 image cache root is invalid"
        ) from exc


__all__ = [
    "P10VisualReviewV2ImageCacheError",
    "P10VisualReviewV2ImageCacheKey",
    "P10VisualReviewV2ImageCacheNotFound",
    "P10VisualReviewV2ImageReplayCache",
]
