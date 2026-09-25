"""Bounded process-local memoization after the caller verifies candidate contents."""
from collections import OrderedDict
from threading import RLock
import json

from ..targets.character43.motion_geometry_details import build


class GeometryCache:
    def __init__(self, *, entries=4, max_bytes=32 << 20):
        if any(type(v) is not int or v < 1 for v in (entries, max_bytes)):
            raise ValueError('motion_geometry_cache_budget')
        self.entries, self.max_bytes = entries, max_bytes
        self._values = OrderedDict()
        self._bytes = 0
        self._lock = RLock()

    def read(self, files, artifact):
        # Callers must run context()/store.read on EVERY request, including hits.
        # Only immutable diagnostic bytes are retained, never files or decisions.
        # Serialize cold work to avoid concurrent repeated full-scene inspection.
        with self._lock:
            if artifact in self._values:
                self._values.move_to_end(artifact)
                return self._values[artifact]
            report = build(files, artifact)
            if report['artifact_sha256'] != artifact:
                raise ValueError('motion_geometry_cache_identity')
            raw = json.dumps(report, ensure_ascii=False, allow_nan=False).encode('utf-8')
            if len(raw) <= self.max_bytes:
                while self._values and (len(self._values) >= self.entries or
                                       self._bytes + len(raw) > self.max_bytes):
                    _, removed = self._values.popitem(last=False)
                    self._bytes -= len(removed)
                self._values[artifact] = raw
                self._bytes += len(raw)
            return raw


_cache = GeometryCache()


def read(files, artifact):
    return _cache.read(files, artifact)
