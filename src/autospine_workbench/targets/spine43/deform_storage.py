"""Shorter deform numbers with identical typed-array import, not motion reduction."""
from copy import deepcopy
from functools import lru_cache
import math
import numpy as np


def _short(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError('deform_storage_nonfinite')
    if value == 0: return value
    return _short_nonzero(value)


@lru_cache(maxsize=8192)
def _short_nonzero(value):
    with np.errstate(over='ignore'):
        converted = np.float32(value)
    if not np.isfinite(converted):
        raise ValueError('deform_storage_float32_overflow')
    candidate = float(str(converted))
    if np.float32(candidate).tobytes() != converted.tobytes():
        raise ValueError('deform_storage_roundtrip')
    # Keep signed zero and integral encodings as supplied; do not enlarge them.
    return candidate if value != 0 and len(repr(candidate)) < len(repr(value)) else value


def compact(document):
    candidate = deepcopy(document); total = changed = 0
    for animation in candidate.get('animations', {}).values():
        for skin in animation.get('attachments', {}).values():
            for slot in skin.values():
                for attachment in slot.values():
                    for frame in attachment.get('deform', []):
                        if 'vertices' not in frame: continue
                        values = frame['vertices']
                        if not isinstance(values, list): raise ValueError('deform_storage_vertices')
                        result = [_short(v) for v in values]
                        total += len(values); changed += sum(a != b for a, b in zip(values, result))
                        frame['vertices'] = result
    return candidate, dict(profile='spine43-deform-float32-text-v1', values=total, changed_values=changed,
                          scope='typed_array_import_equivalence_requires_runtime_verification',
                          authority='none', selected=False)
