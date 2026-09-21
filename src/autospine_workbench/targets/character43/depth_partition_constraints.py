"""Translate sampled render-region traces to explicit ordering requirements."""
from collections import Counter


def build(partition,traces,observations):
    pairs=[];counts=Counter()
    for region in partition['regions']:
        source=region['source_slot'];slot=region['slot']
        signature=traces[source]['groups'][region['group']];rows=observations[source]
        if len(signature)!=len(rows):raise ValueError('partition_constraint_sample_inventory')
        by_body={}
        for state,row in zip(signature,rows):
            if state not in 'FBMAUN':raise ValueError('partition_constraint_state')
            body=row['body'];counts[state]+=1
            by_body.setdefault(body,[]).append(dict(time=row['time'],source_tick=row['source_tick'],
                state=state,required_front=slot if state=='F' else body if state=='B' else None,
                reason_code={'F':'uniform_front','B':'uniform_back','N':'no_sampled_overlap',
                    'M':'within_region_front_back_mixed','A':'depth_margin_ambiguity','U':'unknown_or_unmeasured'}[state]))
        for body,samples in by_body.items():
            if any(b['time']<=a['time'] for a,b in zip(samples,samples[1:])):
                raise ValueError('partition_constraint_time_order')
            transitions=[];last=None
            for sample in samples:
                front=sample['required_front']
                if front is not None:
                    if last is not None and last['required_front']!=front:
                        transitions.append(dict(from_time=last['time'],to_time=sample['time'],
                            from_front=last['required_front'],to_front=front,status='needs_interval_validation'))
                    last=sample
            pairs.append(dict(region=slot,source_slot=source,body=body,samples=samples,transitions=transitions))
    return dict(profile='sampled-render-region-order-constraints-v1',pairs=pairs,counts=dict(counts),
        authority='none',selected=False,scope='sample_constraints_not_draw_order_or_hysteresis_acceptance')
