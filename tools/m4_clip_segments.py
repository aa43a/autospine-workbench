"""Bound topology-stable clipping intervals and their shared endpoint approximations."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import numpy as np
from m4_clip_correspondence import build,distance


def partition(rows, *, segment_limit=64):
    if not rows or any(r['status']!='single_loop' for r in rows):raise ValueError('clip_segment_single_loop')
    groups=[]
    for i,row in enumerate(rows):
        keys=[tuple(k) for k in row['loops'][0]['vertex_keys']]
        start=keys.index(min(keys));signature=tuple(keys[start:]+keys[:start])
        if groups and groups[-1]['signature']==signature:groups[-1]['end']=i
        else:groups.append(dict(start=i,end=i,signature=signature))
    if len(groups)>segment_limit:raise ValueError('clip_segment_count_budget')
    segments=[]
    for group in groups:
        end=min(group['end']+1,len(rows)-1)
        result=build(rows[group['start']:end+1],anchor_edges=True,exact_endpoints=True)
        segments.append(dict(start=rows[group['start']]['time'],end=rows[end]['time'],**result))
    joins=[]
    for a,b in zip(segments,segments[1:]):
        if a['frames'][-1]['time']!=b['frames'][0]['time']:raise ValueError('clip_segment_join_time')
        p=np.asarray(a['frames'][-1]['points']);q=np.asarray(b['frames'][0]['points'])
        error=max(distance(p,np.concatenate((q,q[:1]))),distance(q,np.concatenate((p,p[:1]))))
        joins.append(dict(time=b['start'],sampled_boundary_difference_px=error))
    return dict(authority='none',selected=False,segments=segments,joins=joins,segment_limit=segment_limit,
                scope='topology_local_anchor_correspondence_not_interpolation_or_runtime_acceptance')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path);parser.add_argument('output',type=Path);args=parser.parse_args()
    raw=args.source.read_bytes();source=json.loads(raw)
    result=partition(source['rows']);result.update(parent=source['candidate'],contour_sha256=sha256(raw).hexdigest())
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x',encoding='utf-8') as stream:json.dump(result,stream)
    print(json.dumps(dict(segments=len(result['segments']),maximum_vertices=max(s['vertex_count'] for s in result['segments']),
        maximum_boundary_error=max(s['maximum_sampled_boundary_error_px'] for s in result['segments']),
        maximum_join_error=max((j['sampled_boundary_difference_px'] for j in result['joins']),default=0))))
