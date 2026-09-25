"""Separate within-frame depth mixing from ordinary temporal side changes."""
from collections import Counter


def summarize(records):
    pairs={}
    for record in records:
        if 'triangle_observations' not in record:
            raise ValueError('depth_triangle_trace_required')
        pair=tuple(record['pair']);group=pairs.setdefault(pair,dict(triangles={},incomplete=[]))
        time=record['check']['time']
        if not record['trace_complete']:
            group['incomplete'].append(time)
            continue
        seen=set()
        for observation in record['triangle_observations']:
            index=observation['triangle'];counts=observation['counts']
            if (type(index) is not int or index<0 or index in seen or
                set(counts)-{'front','back','ambiguous','unknown'} or
                any(type(v) is not int or v<0 for v in counts.values())):
                raise ValueError('depth_triangle_observation_invalid')
            seen.add(index)
            if not sum(counts.values()):continue
            row=group['triangles'].setdefault(index,dict(triangle=index,samples=0,
                front_times=[],back_times=[],mixed_times=[],uncertain_times=[]))
            row['samples']+=1
            front,back=counts.get('front',0),counts.get('back',0)
            if front and back:row['mixed_times'].append(time)
            elif front:row['front_times'].append(time)
            elif back:row['back_times'].append(time)
            if counts.get('ambiguous',0) or counts.get('unknown',0):row['uncertain_times'].append(time)
    result=[]
    for pair,group in pairs.items():
        triangles=[]
        for _,row in sorted(group['triangles'].items()):
            state=('within_frame_mixed' if row['mixed_times'] else
                   'uncertain_depth' if row['uncertain_times'] else
                   'temporal_side_change' if row['front_times'] and row['back_times'] else
                   'observed_front_only' if row['front_times'] else 'observed_back_only')
            triangles.append(dict(row,status=state))
        result.append(dict(pair=list(pair),triangles=triangles,
            counts=dict(Counter(r['status'] for r in triangles)),incomplete_times=group['incomplete']))
    return dict(profile='depth-triangle-localization-v1',pairs=result,authority='none',selected=False,
        scope='sampled_overlap_triangles_not_complete_surface_ownership_or_order_adoption')
