"""Short-lived, non-authoritative read sessions for P10.3c images."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
import re
import secrets
from threading import RLock
import time

from .body_sway_visual_review_application_models_v2 import (
    BodySwayVisualReviewImageV2,
)
from .p10_visual_review_v2_image_cache import (
    MAX_IMAGE_CACHE_BYTES,
    P10VisualReviewV2ImageCacheKey,
    P10VisualReviewV2ImageReplayCache,
)


DEFAULT_IMAGE_SESSION_TTL_SECONDS = 120
MAX_IMAGE_SESSIONS = 8
_TOKEN = re.compile(r"[A-Za-z0-9_-]{43}")


class P10VisualReviewV2ImageSessionError(RuntimeError):
    pass


class P10VisualReviewV2ImageSessionNotFound(
    P10VisualReviewV2ImageSessionError,
):
    pass


@dataclass(frozen=True, slots=True)
class P10VisualReviewV2ImageSession:
    token: str
    expires_in_seconds: int

    def public_document(self) -> dict[str, object]:
        return {
            "format_version": 1,
            "token": self.token,
            "expires_in_seconds": self.expires_in_seconds,
            "authority": "read_only_snapshot",
        }


@dataclass(frozen=True, slots=True)
class _Binding:
    key: P10VisualReviewV2ImageCacheKey
    images: tuple[BodySwayVisualReviewImageV2, ...]
    size_bytes: int
    expires_at: float


class P10VisualReviewV2ImageSessionStore:
    """Bind a random read token to one already-verified immutable snapshot.

    A session can only serve captured PNG bytes. It is never consulted by
    history or decision PUT, and it expires even while a page remains open.
    """

    def __init__(
        self, state_root: Path, *,
        image_cache: P10VisualReviewV2ImageReplayCache | None = None,
        capacity: int = MAX_IMAGE_SESSIONS,
        byte_capacity: int = MAX_IMAGE_CACHE_BYTES,
        ttl_seconds: int = DEFAULT_IMAGE_SESSION_TTL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
        token_factory: Callable[[], str] = lambda: secrets.token_urlsafe(32),
    ) -> None:
        if type(capacity) is not int or not 1 <= capacity <= MAX_IMAGE_SESSIONS:
            raise P10VisualReviewV2ImageSessionError(
                "Visual review image session capacity is invalid"
            )
        if type(ttl_seconds) is not int or not 1 <= ttl_seconds <= 600:
            raise P10VisualReviewV2ImageSessionError(
                "Visual review image session lifetime is invalid"
            )
        if type(byte_capacity) is not int \
                or not 1 <= byte_capacity <= MAX_IMAGE_CACHE_BYTES:
            raise P10VisualReviewV2ImageSessionError(
                "Visual review image session byte capacity is invalid"
            )
        if not callable(clock) or not callable(token_factory):
            raise P10VisualReviewV2ImageSessionError(
                "Visual review image session dependencies are invalid"
            )
        self._cache = image_cache or P10VisualReviewV2ImageReplayCache(
            state_root,
        )
        if not self._cache.owns_state_root(state_root):
            raise P10VisualReviewV2ImageSessionError(
                "Visual review image session belongs to another store"
            )
        self._capacity = capacity
        self._byte_capacity = byte_capacity
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._token_factory = token_factory
        self._bindings: OrderedDict[str, _Binding] = OrderedDict()
        self._lock = RLock()

    @property
    def image_cache(self) -> P10VisualReviewV2ImageReplayCache:
        return self._cache

    def owns_state_root(self, state_root: Path) -> bool:
        return self._cache.owns_state_root(state_root)

    def open(
        self, key: P10VisualReviewV2ImageCacheKey, *,
        loader: Callable[[], tuple[BodySwayVisualReviewImageV2, ...]],
    ) -> P10VisualReviewV2ImageSession:
        if type(key) is not P10VisualReviewV2ImageCacheKey \
                or not callable(loader):
            raise P10VisualReviewV2ImageSessionError(
                "Visual review image session request is invalid"
            )
        images = self._cache.snapshot(key, loader=loader)
        weight = sum(image.size_bytes for image in images)
        if weight > self._byte_capacity:
            raise P10VisualReviewV2ImageSessionError(
                "Visual review image session snapshot is too large"
            )
        now = self._clock()
        with self._lock:
            self._discard_expired(now)
            token = self._unique_token()
            resident = sum(row.size_bytes for row in self._bindings.values())
            while self._bindings and (
                len(self._bindings) >= self._capacity
                or resident + weight > self._byte_capacity
            ):
                _, removed = self._bindings.popitem(last=False)
                resident -= removed.size_bytes
            self._bindings[token] = _Binding(
                key, images, weight, now + self._ttl_seconds,
            )
        return P10VisualReviewV2ImageSession(
            token, self._ttl_seconds,
        )

    def image(
        self, token: str, *, job_id: str, candidate_sha256: str,
        case_id: str, png_sha256: str,
    ) -> BodySwayVisualReviewImageV2 | None:
        """Return None only when the token is absent, malformed, or expired."""

        if type(token) is not str or _TOKEN.fullmatch(token) is None:
            return None
        now = self._clock()
        with self._lock:
            self._discard_expired(now)
            binding = self._bindings.get(token)
            if binding is None:
                return None
            self._bindings.move_to_end(token)
        if binding.key.job_id != job_id \
                or binding.key.candidate_sha256 != candidate_sha256:
            raise P10VisualReviewV2ImageSessionNotFound(
                "Visual review image session is cross-wired"
            )
        return self._cache.image(
            binding.key, case_id=case_id, png_sha256=png_sha256,
            loader=lambda: binding.images,
        )

    def _discard_expired(self, now: float) -> None:
        expired = [
            token for token, binding in self._bindings.items()
            if binding.expires_at <= now
        ]
        for token in expired:
            self._bindings.pop(token, None)

    def _unique_token(self) -> str:
        for _attempt in range(8):
            token = self._token_factory()
            if type(token) is str and _TOKEN.fullmatch(token) \
                    and token not in self._bindings:
                return token
        raise P10VisualReviewV2ImageSessionError(
            "Visual review image session token is unavailable"
        )


__all__ = [
    "DEFAULT_IMAGE_SESSION_TTL_SECONDS",
    "P10VisualReviewV2ImageSession",
    "P10VisualReviewV2ImageSessionError",
    "P10VisualReviewV2ImageSessionNotFound",
    "P10VisualReviewV2ImageSessionStore",
]
