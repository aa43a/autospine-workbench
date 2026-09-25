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


def timeline(document, animation, slot, reference):
    """Exact held-order intervals, without extending an event's material decision."""
    from .region_order_interval import duration
    motion=document['animations'][animation]
    keys=motion.get('drawOrder',[])
    scope='order_intervals_only_not_material_relation_for_all_times_or_visual_acceptance'
    if len(keys)>1024:
        return dict(status='unmeasured',reason_code='occlusion_order_timeline_budget',scope=scope)
    # Inspect validates all key times, including Float32 collisions and legacy keys.
    initial=inspect(document,animation,0,slot,reference)
    end=struct.unpack('f',struct.pack('f',duration(motion)))[0]
    ticks=sorted({0.,end,*(struct.unpack('f',struct.pack('f',k.get('time',0)))[0] for k in keys)})
    intervals=[]
    for start,stop in zip(ticks,ticks[1:]):
        result=initial if start==0 else inspect(document,animation,start,slot,reference)
        front=result['reference_can_cover_in_order']
        if intervals and intervals[-1]['reference_can_cover_in_order']==front:
            intervals[-1]['end']=stop
        else:
            intervals.append(dict(start=start,end=stop,reference_can_cover_in_order=front))
    endpoint=inspect(document,animation,end,slot,reference)
    return dict(status='measured',duration=end,intervals=intervals,interval_convention='start_inclusive_end_exclusive',
                endpoint=dict(time=end,reference_can_cover_in_order=endpoint['reference_can_cover_in_order']),
                scope=scope,authority='none',selected=False)
