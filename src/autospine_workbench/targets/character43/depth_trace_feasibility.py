"""Determine what existing-triangle splitting can express across depth hypotheses."""
from collections import Counter


def inspect(hypotheses,triangle_count):
    if not hypotheses or type(triangle_count) is not int or triangle_count<1:
        raise ValueError('trace_feasibility_inventory')
    supported=[]
    for h in hypotheses:
        if 'triangles' not in h:raise ValueError('trace_feasibility_missing_trace')
        indexed={}
        for key,value in h['triangles'].items():
            index=int(key)
            if str(index)!=str(key) or not 0<=index<triangle_count or index in indexed:
                raise ValueError('trace_feasibility_triangle_index')
            if set(value)!={'front','back','ambiguous','unknown'} or any(type(v) is not int or v<0 for v in value.values()):
                raise ValueError('trace_feasibility_counts')
            indexed[index]=value
        supported.append(indexed)
    rows=[]
    for index in sorted(set().union(*(set(s) for s in supported))):
        counts=[s.get(index,dict.fromkeys(('front','back','ambiguous','unknown'),0)) for s in supported]
        totals=[sum(c.values()) for c in counts]
        if len(set(totals))!=1 or totals[0]<=0:raise ValueError('trace_feasibility_hypothesis_coverage')
        stable_front=all(c['front']==totals[0] for c in counts)
        stable_back=all(c['back']==totals[0] for c in counts)
        mixed=any(c['front']>0 and c['back']>0 for c in counts)
        status='stable_front' if stable_front else 'stable_back' if stable_back else 'unresolved'
        rows.append(dict(triangle=index,status=status,overlap_pixels=totals[0],
                         opposing_pixels_within_triangle=mixed,
                         unresolved_interval=any(c['ambiguous'] or c['unknown'] for c in counts)))
    return dict(triangles=rows,counts=dict(Counter(r['status'] for r in rows)),
        requires_subtriangle_or_model_change=any(r['opposing_pixels_within_triangle'] for r in rows),
        existing_triangle_split_fully_decidable=all(r['status']!='unresolved' for r in rows),
        scope='sampled_proxy_hypotheses_not_observed_surface_or_candidate_acceptance')
