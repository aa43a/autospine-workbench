"""Necessary draw-order evidence for a covering relationship, not pixel coverage."""
import math
import struct
from ...spine42_draw_order_offsets import apply_spine42_draw_order_offsets


def inspect(document, animation, time, slot, reference):
    if type(time) not in (int,float) or not math.isfinite(time) or time<0:
        raise ValueError('occlusion_order_time_invalid')
    names=[s['name'] for s in document['slots']]
    if slot==reference or slot not in names or reference not in names:
        raise ValueError('occlusion_order_slots_invalid')
    motion=document['animations'][animation]
    if 'draworder' in motion:raise ValueError('occlusion_order_legacy_key_unsupported')
    selected=None; previous=-1.
    for key in motion.get('drawOrder',[]):
        timestamp=key.get('time',0)
        if type(timestamp) not in (int,float) or not math.isfinite(timestamp) or timestamp<0:
            raise ValueError('occlusion_order_key_time_invalid')
        try:effective=struct.unpack('f',struct.pack('f',timestamp))[0]
        except (OverflowError,struct.error) as error:
            raise ValueError('occlusion_order_key_time_invalid') from error
        if not math.isfinite(effective) or effective<=previous:
            raise ValueError('occlusion_order_key_time_collision')
        previous=effective
        if effective<=time:selected=key
    order=apply_spine42_draw_order_offsets(names,selected.get('offsets',[]) if selected else [])
    front=order.index(reference)>order.index(slot)
    return dict(status='reference_in_front' if front else 'reference_behind',
        reference_can_cover_in_order=front,slot_index=order.index(slot),
        reference_index=order.index(reference),order=list(order),
        sampled_time=time,source_key_time=None if selected is None else selected.get('time',0),
        scope='draw_order_only_not_alpha_overlap_or_visual_acceptance')
