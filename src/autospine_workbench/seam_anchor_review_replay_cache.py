"""Bounded server-local replay cache for exact seam-review inputs."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable
from pathlib import Path
from threading import RLock
from typing import TypeVar

from .mesh_source_images import VerifiedMeshSource, VerifiedMeshSourceReader
from .seam_anchor_review_address import ExactSeamAnchorReviewAddress
from .seam_anchor_review_candidate_binding import (
    BoundSeamAnchorReviewCandidate,
    load_bound_seam_anchor_review_candidate,
)
_T = TypeVar("_T")
_MAX_CAPACITY = 16
MAX_CANDIDATE_CACHE_BYTES = 16 * 1024 * 1024
MAX_SOURCE_CACHE_BYTES = 128 * 1024 * 1024


class SeamAnchorReviewReplayCacheError(RuntimeError):
    """Raised when a replay cache is configured or addressed unsafely."""


class SeamAnchorReviewReplayCache:
    """Single-flight immutable snapshots retained until LRU eviction/restart.

    Decisions and revision history never enter this cache.  Resident exact
    content addresses are trusted only because both loaders fully verify them
    before returning; an operator must restart after out-of-contract mutation.
    """

    def __init__(
        self,
        state_root: Path,
        *,
        candidate_capacity: int = 4,
        source_capacity: int = 2,
        candidate_byte_capacity: int = MAX_CANDIDATE_CACHE_BYTES,
        source_byte_capacity: int = MAX_SOURCE_CACHE_BYTES,
    ) -> None:
        self._state_root = _resolved_root(state_root)
        self._candidate_capacity = _capacity(
            candidate_capacity, "candidate"
        )
        self._source_capacity = _capacity(source_capacity, "source")
        self._candidate_byte_capacity = _byte_capacity(
            candidate_byte_capacity, MAX_CANDIDATE_CACHE_BYTES, "candidate"
        )
        self._source_byte_capacity = _byte_capacity(
            source_byte_capacity, MAX_SOURCE_CACHE_BYTES, "source"
        )
        self._candidates: OrderedDict[
            ExactSeamAnchorReviewAddress, BoundSeamAnchorReviewCandidate
        ] = OrderedDict()
        self._sources: OrderedDict[
            ExactSeamAnchorReviewAddress, VerifiedMeshSource
        ] = OrderedDict()
        self._candidate_lock = RLock()
        self._source_lock = RLock()

    @property
    def state_root(self) -> Path:
        return self._state_root

    def owns_state_root(self, state_root: Path) -> bool:
        """Return whether a consumer is bound to this exact state root."""

        return self._state_root == _resolved_root(state_root)

    def load_candidate(
        self, address: ExactSeamAnchorReviewAddress,
    ) -> BoundSeamAnchorReviewCandidate:
        """Replay one candidate once, then retain only its immutable value."""

        return self._load(
            address, self._candidates, self._candidate_lock,
            self._candidate_capacity, self._candidate_byte_capacity,
            lambda: load_bound_seam_anchor_review_candidate(
                self._state_root, address
            ),
            BoundSeamAnchorReviewCandidate,
            lambda value: value.cache_weight_bytes, "candidate",
        )

    def load_source(
        self, address: ExactSeamAnchorReviewAddress,
    ) -> VerifiedMeshSource:
        """Replay one verified P3 image source once per resident address."""

        return self._load(
            address, self._sources, self._source_lock,
            self._source_capacity, self._source_byte_capacity,
            lambda: VerifiedMeshSourceReader(self._state_root).load(
                *address.mesh_reader_arguments
            ),
            VerifiedMeshSource,
            lambda value: value.cache_weight_bytes, "source",
        )

    @staticmethod
    def _load(
        address: ExactSeamAnchorReviewAddress,
        values: OrderedDict[ExactSeamAnchorReviewAddress, _T],
        lock: RLock,
        capacity: int,
        byte_capacity: int,
        loader: Callable[[], _T],
        expected_type: type[_T],
        weight_of: Callable[[_T], int],
        label: str,
    ) -> _T:
        if type(address) is not ExactSeamAnchorReviewAddress:
            raise SeamAnchorReviewReplayCacheError(
                "Replay cache requires an exact seam-review address"
            )
        with lock:
            try:
                value = values.pop(address)
            except KeyError:
                value = loader()
                if type(value) is not expected_type:
                    raise SeamAnchorReviewReplayCacheError(
                        f"Verified seam-review {label} loader returned an invalid value"
                    )
                weight = weight_of(value)
                if type(weight) is not int or weight < 0:
                    raise SeamAnchorReviewReplayCacheError(
                        f"Verified seam-review {label} weight is invalid"
                    )
                if weight > byte_capacity:
                    return value
                resident = sum(weight_of(item) for item in values.values())
                while values and (
                    len(values) >= capacity
                    or resident + weight > byte_capacity
                ):
                    _, removed = values.popitem(last=False)
                    resident -= weight_of(removed)
            values[address] = value
            return value


def _capacity(value: int, label: str) -> int:
    if type(value) is not int or not 1 <= value <= _MAX_CAPACITY:
        raise SeamAnchorReviewReplayCacheError(
            f"Seam-review {label} cache capacity is invalid"
        )
    return value


def _byte_capacity(value: int, maximum: int, label: str) -> int:
    if type(value) is not int or not 1 <= value <= maximum:
        raise SeamAnchorReviewReplayCacheError(
            f"Seam-review {label} cache byte capacity is invalid"
        )
    return value


def _resolved_root(value: Path) -> Path:
    try:
        return Path(value).expanduser().resolve()
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise SeamAnchorReviewReplayCacheError(
            "Seam-review cache state root is invalid"
        ) from exc
