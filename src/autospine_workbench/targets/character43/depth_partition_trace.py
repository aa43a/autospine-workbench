"""Stable render groups from complete per-triangle temporal depth signatures."""
from collections import Counter
from hashlib import sha256
import math


def classify(counts):
    if any(k not in ('front','back','ambiguous','unknown') or type(v) is not int or v<0
           for k,v in counts.items()):raise ValueError('triangle_depth_counts_invalid')
    if counts.get('unknown'):return 'U'
    if counts.get('front') and counts.get('back'):return 'M'
    if counts.get('ambiguous'):return 'A'
    if counts.get('front'):return 'F'
    if counts.get('back'):return 'B'
    return 'N'


def labels(triangle_count, samples):
    if type(triangle_count) is not int or triangle_count<1 or not samples:
        raise ValueError('triangle_depth_trace_empty')
    signatures=['']*triangle_count;seen=set();totals=Counter()
    for row in samples:
        key=(row['body'],row['time'])
        if not math.isfinite(row['time']) or key in seen:raise ValueError('triangle_depth_trace_time')
        seen.add(key)
        counts=row['triangles']
        if any(type(t) is not int or not 0<=t<triangle_count for t in counts):
            raise ValueError('triangle_depth_trace_inventory')
        if row['status']=='unmeasured':
            # A budget exception may have emitted partial callbacks. Discard all.
            frame=['U']*triangle_count
        elif row['status'] in ('no_overlap','uniform_front_proxy','uniform_back_proxy','requires_partition_or_more_depth'):
            if row['status']=='no_overlap' and counts:raise ValueError('triangle_depth_trace_overlap')
            frame=[classify(counts.get(t,{})) for t in range(triangle_count)]
        else:raise ValueError('triangle_depth_trace_status')
        for t,value in enumerate(frame):signatures[t]+=value
        totals.update(frame)
    groups={};result=[]
    for signature in signatures:
        name='depth-'+sha256(signature.encode()).hexdigest()
        groups[name]=signature;result.append(name)
    return result,dict(profile='sampled-temporal-triangle-depth-signature-v1',groups=groups,
        samples=len(samples),triangle_samples=dict(totals),
        legend=dict(F='front',B='back',M='mixed',A='margin',U='unknown_or_unmeasured',N='no_sampled_overlap'),
        authority='none',selected=False,scope='render_groups_not_order_or_visual_acceptance')
