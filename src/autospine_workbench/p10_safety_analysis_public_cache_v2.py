"""Single-entry bounded cache for already validated public receipts."""

from __future__ import annotations

from copy import deepcopy
import json
import threading


MAX_PUBLIC_CACHE_BYTES = 8 * 1024 * 1024


class P10SafetyAnalysisPublicCacheV2:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entry: tuple[str, dict] | None = None

    def get(self, run_id: str):
        with self._lock:
            if self._entry is None or self._entry[0] != run_id:
                return None
            return deepcopy(self._entry[1])

    def put(self, run_id: str, document: dict) -> None:
        raw = json.dumps(
            document, ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
        with self._lock:
            self._entry = (
                (run_id, deepcopy(document))
                if len(raw) <= MAX_PUBLIC_CACHE_BYTES else None
            )


__all__ = [
    "MAX_PUBLIC_CACHE_BYTES", "P10SafetyAnalysisPublicCacheV2",
]
