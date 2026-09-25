"""Compose an explicit region move with an existing painter-order timeline."""
import struct

from ...spine42_draw_order_offsets import (
    apply_spine42_draw_order_offsets as decode,
    encode_spine42_draw_order_offsets as encode,
)


def merge(names, keys, moved_names, reference, side, interval):
    # Source keys have already been validated by partition_draw_order.remap.
    def runtime(t):
        return struct.unpack('<f', struct.pack('<f', t))[0]

    start, end = map(runtime, interval)
    events = {runtime(k.get('time', 0)): k for k in keys}
    for t in interval:
        events.setdefault(runtime(t), {'time': t})
    if len(events) > 4096:
        raise ValueError('region_order_key_limit')
    source_events = {runtime(k.get('time', 0)): k for k in keys}
    source_order = list(names)
    output = []
    for tick, key in sorted(events.items()):
        if tick in source_events:
            source_order = list(decode(names, source_events[tick].get('offsets', [])))
        order = source_order
        if start <= tick < end:
            moved = [name for name in order if name in moved_names]
            retained = [name for name in order if name not in moved_names]
            index = retained.index(reference) + (side == 'after')
            order = retained[:index] + moved + retained[index:]
        item = {'offsets': encode(names, order)}
        if 'time' in key:
            item['time'] = key['time']
        output.append(item)
    return output
