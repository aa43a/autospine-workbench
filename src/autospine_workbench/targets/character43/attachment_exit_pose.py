"""Evaluate the outgoing attachment at an exact Runtime switch boundary."""
from copy import deepcopy
import struct


def exits(document, animation, slot):
    previous=next(s.get('attachment') for s in document['slots'] if s['name']==slot)
    rows=[];last=-1.
    for key in document['animations'][animation].get('slots',{}).get(slot,{}).get('attachment',[]):
        time=struct.unpack('f',struct.pack('f',key.get('time',0)))[0]
        if not 0<=time or time<=last:raise ValueError('attachment_exit_key_order')
        current=key.get('name')
        if previous is not None and previous!=current and time>0:
            rows.append(dict(time=time,attachment=previous,next_attachment=current))
        previous=current;last=time
    return rows


def outgoing_document(document, animation, slot, attachment, time):
    if not any(row['time']==time and row['attachment']==attachment for row in exits(document,animation,slot)):
        raise ValueError('attachment_exit_not_a_verified_boundary')
    result=deepcopy(document)
    next(s for s in result['slots'] if s['name']==slot)['attachment']=attachment
    result['animations'][animation]['slots'][slot].pop('attachment')
    return result
