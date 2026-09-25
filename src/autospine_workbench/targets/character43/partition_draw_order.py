"""Expand a source slot into ordered render parts at every existing order key."""
from copy import deepcopy
import math
import struct
from ...spine42_draw_order_offsets import (
    apply_spine42_draw_order_offsets as decode,
    encode_spine42_draw_order_offsets as encode,
)


def remap(original, candidate, regions):
    source=[s['name'] for s in original['slots']]
    target=[s['name'] for s in candidate['slots']]
    replacements={}
    for row in regions:
        replacements.setdefault(row['source_slot'],[]).append(row['slot'])
    def expand(order):
        return [part for name in order for part in replacements.get(name,[name])]
    if expand(source)!=target:
        raise ValueError('partition_order_setup_mismatch')
    count=0
    for name,animation in original['animations'].items():
        if 'draworder' in animation:
            raise ValueError('partition_order_legacy_unsupported')
        if 'drawOrder' not in animation:
            continue
        keys=animation['drawOrder']
        if len(keys)>4096:
            raise ValueError('partition_order_key_limit')
        output=[]; previous=-1.
        for key in keys:
            if set(key)-{'time','offsets'}:
                raise ValueError('partition_order_key_fields')
            timestamp=key.get('time',0)
            if type(timestamp) not in (int,float) or not math.isfinite(timestamp) or timestamp<0:
                raise ValueError('partition_order_time_invalid')
            try: stored=struct.unpack('f',struct.pack('f',timestamp))[0]
            except (OverflowError,struct.error) as error:
                raise ValueError('partition_order_time_invalid') from error
            if not math.isfinite(stored) or stored<=previous:
                raise ValueError('partition_order_time_collision')
            previous=stored
            expanded=expand(decode(source,key.get('offsets',[])))
            item=deepcopy(key);item['offsets']=encode(target,expanded)
            output.append(item)
        candidate['animations'][name]['drawOrder']=output
        count+=len(output)
    return dict(profile='partition-source-order-expansion-v1',key_count=count,
                source_key_times_preserved=True,part_order_preserved=True,
                scope='source_painter_order_preserved_not_occlusion_repair',authority='none')
