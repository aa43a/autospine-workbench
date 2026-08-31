"""Process-wide serialization for one project's authoring identity."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import os
from pathlib import Path
import re
import threading


_PROJECT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_REGISTRY_LOCK = threading.Lock()
_LOCKS: dict[tuple[str, str], threading.RLock] = {}


@contextmanager
def project_authoring_transaction(
    state_root: Path, project_id: str,
) -> Iterator[None]:
    """Serialize normal in-process writes that can change one current chain."""

    if not isinstance(project_id, str) or not _PROJECT_ID.fullmatch(project_id):
        raise ValueError("Project authoring transaction identity is invalid")
    root = os.path.normcase(str(Path(state_root).expanduser().resolve()))
    key = (root, project_id)
    with _REGISTRY_LOCK:
        lock = _LOCKS.setdefault(key, threading.RLock())
    with lock:
        yield


__all__ = ["project_authoring_transaction"]
