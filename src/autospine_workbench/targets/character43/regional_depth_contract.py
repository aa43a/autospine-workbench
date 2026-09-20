"""Admit only exact render partitioning and the reported order keys."""
from copy import deepcopy
from hashlib import sha256
import math

from ...automation.storage_io import canonical_bytes
from .depth_region_partition import build as partition_build

PROFILE = 'verified-regional-depth-transform-v1'


def verify(source, candidate, animation, selected_slots, order):
    if order.get('failures') or order.get('status') not in ('candidate', 'no_visible_order_change'):
        raise ValueError('regional_depth_order_not_admissible')
    expected = partition_build(source, selected_slots)[0] if selected_slots else deepcopy(source)
    slots = [s['name'] for s in expected['slots']]
    if len(slots) != len(set(slots)):
        raise ValueError('regional_depth_slot_inventory')
    keys = []; previous = -1
    for frame in order['frames']:
        time = frame['time']; names = frame['order']
        if (isinstance(time, bool) or not isinstance(time, (int, float)) or
                not math.isfinite(time) or time < 0 or time <= previous):
            raise ValueError('regional_depth_order_time')
        if sorted(names) != sorted(slots):
            raise ValueError('regional_depth_slot_inventory')
        previous = time
        keys.append(dict(time=time, offsets=[dict(slot=s, offset=names.index(s)-i)
                                             for i, s in enumerate(slots)]))
    if keys:
        expected['animations'][animation]['drawOrder'] = keys
    if candidate != expected:
        raise ValueError('regional_depth_unexpected_edit')
    return dict(profile=PROFILE, source_skeleton_sha256=sha256(canonical_bytes(source)).hexdigest(),
        candidate_skeleton_sha256=sha256(canonical_bytes(candidate)).hexdigest(),
        partition_slots=list(selected_slots or []), order_keys=len(keys),
        authority='none', scope='exact_representation_transform_not_runtime_or_visual_acceptance')
