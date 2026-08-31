"""Process-wide transaction lock shared by P10.1 and dependent mutations."""

from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import re
import threading
from collections.abc import Iterator


_SHA = re.compile(r"^[0-9a-f]{64}$")
_REGISTRY_LOCK = threading.Lock()
_LOCKS: dict[tuple[str, str], threading.RLock] = {}


@contextmanager
def idle_behavior_review_transaction(
    state_root: Path, candidate_sha256: str,
) -> Iterator[None]:
    """Serialize a P10.1 head with mutations derived from that exact head."""

    if not isinstance(candidate_sha256, str) \
            or not _SHA.fullmatch(candidate_sha256):
        raise ValueError("Idle behavior candidate identity is invalid")
    root = os.path.normcase(str(Path(state_root).expanduser().resolve()))
    key = (root, candidate_sha256)
    with _REGISTRY_LOCK:
        lock = _LOCKS.setdefault(key, threading.RLock())
    with lock:
        yield
