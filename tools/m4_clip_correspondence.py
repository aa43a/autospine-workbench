"""Anchor contour correspondence; reject approximations exceeding explicit budgets."""
import argparse
from hashlib import sha256
import json
import math
from pathlib import Path
import numpy as np


def resample(points, count):
    p=np.asarray(points,dtype=float);lengths=np.linalg.norm(np.diff(p,axis=0),axis=1)
    distances=np.concatenate(([0.],np.cumsum(lengths)))
    if distances[-1]<=1e-10:raise ValueError('clip_collapsed_anchor_span')
    positions=np.linspace(0,distances[-1],count+1) if isinstance(count,int) else np.asarray(count)*distances[-1]
    return np.column_stack([np.interp(positions,distances,p[:,axis]) for axis in (0,1)])


def distance(points, line):
    a=line[:-1];delta=np.diff(line,axis=0);den=np.sum(delta*delta,axis=1)
    t=np.clip(np.sum((points[:,None,:]-a)*delta,axis=2)/np.maximum(den,1e-20),0,1)
    return float(np.linalg.norm(points[:,None,:]-(a+t[:,:,None]*delta),axis=2).min(axis=1).max())


def worst_corner(points,line):
    p=np.asarray(points);a=line[:-1];delta=np.diff(line,axis=0);den=np.sum(delta*delta,axis=1)
    t=np.clip(np.sum((p[:,None,:]-a)*delta,axis=2)/np.maximum(den,1e-20),0,1)
    errors=np.linalg.norm(p[:,None,:]-(a+t[:,:,None]*delta),axis=2).min(axis=1)
    index=int(errors.argmax());arc=np.concatenate(([0.],np.cumsum(np.linalg.norm(np.diff(p,axis=0),axis=1))))
    return float(errors[index]),float(arc[index]/arc[-1])


def build(rows, tolerance=.1, limit=512, *, anchor_edges=False, exact_endpoints=False):
    if not rows or not math.isfinite(tolerance) or tolerance<=0 or type(limit) is not int or limit<3:
        raise ValueError('clip_correspondence_options')
    if any(r['status']!='single_loop' or len(r['loops'])!=1 for r in rows):
        raise ValueError('clip_single_loop_required')
    for row in rows:
        loop=row['loops'][0];points=loop['points'];keys=[tuple(k) for k in loop['vertex_keys']]
        if (len(points)<3 or len(points)!=len(keys) or len(set(keys))!=len(keys) or
                any(len(p)!=2 or any(not math.isfinite(v) for v in p) for p in points)):
            raise ValueError('clip_contour_input_invalid')
    times=[r['time'] for r in rows]
    if any(not math.isfinite(t) for t in times) or any(b<=a for a,b in zip(times,times[1:])):
        raise ValueError('clip_correspondence_times')
    common=set.intersection(*[{tuple(k) for k in r['loops'][0]['vertex_keys'] if anchor_edges or k[0]=='v'} for r in rows])
    if len(common)<3:raise ValueError('clip_stable_anchors_missing')
    anchor=min(common);spans=[];expected=None
    for row in rows:
        loop=row['loops'][0];keys=[tuple(k) for k in loop['vertex_keys']];points=loop['points']
        start=keys.index(anchor);keys=keys[start:]+keys[:start];points=points[start:]+points[:start]
        indices=[i for i,k in enumerate(keys) if k in common];order=[keys[i] for i in indices]
        if expected is not None and order!=expected:raise ValueError('clip_anchor_order_changed')
        expected=order;indices.append(len(keys));points=points+[points[0]]
        spans.append([points[a:b+1] for a,b in zip(indices,indices[1:])])
    parameters=[list(np.linspace(0,1,max(len(frame[i])-1 for frame in spans)+1)) for i in range(len(expected))]
    if exact_endpoints:
        for i,values in enumerate(parameters):
            for frame in (spans[0],spans[-1]):
                arc=np.concatenate(([0.],np.cumsum(np.linalg.norm(np.diff(frame[i],axis=0),axis=1))))
                if arc[-1]<=1e-10:raise ValueError('clip_collapsed_anchor_span')
                values.extend((arc/arc[-1]).tolist())
            parameters[i]=sorted(set(values))
    sampled=[[None for _ in expected] for _ in spans]
    errors=[0.]*len(expected);pending=list(range(len(expected)))
    while True:
        counts=[len(p)-1 for p in parameters]
        if sum(counts)>limit:raise ValueError('clip_correspondence_vertex_budget')
        for i in pending:
            for frame,candidate in zip(spans,sampled):candidate[i]=resample(frame[i],parameters[i])
            errors[i]=max(max(distance(np.asarray(frame[i]),candidate[i]),distance(candidate[i],np.asarray(frame[i])))
                          for frame,candidate in zip(spans,sampled))
        bad=[i for i,error in enumerate(errors) if error>tolerance]
        if not bad:break
        for i in bad:
            error,parameter=max(worst_corner(frame[i],candidate[i]) for frame,candidate in zip(spans,sampled))
            if any(abs(parameter-p)<1e-12 for p in parameters[i]):raise ValueError('clip_correspondence_stalled')
            parameters[i]=sorted(parameters[i]+[parameter])
        pending=bad
    return dict(authority='none',selected=False,anchor_keys=[list(k) for k in expected],span_counts=counts,
                span_parameters=parameters,vertex_count=sum(counts),tolerance_px=tolerance,maximum_sampled_boundary_error_px=max(errors),
                exact_endpoints=exact_endpoints,error_scope='bidirectional_polyline_vertex_distance_not_continuous_hausdorff_or_depth_safety',
                frames=[dict(time=t,points=np.concatenate([p[:-1] for p in candidate]).tolist()) for t,candidate in zip(times,sampled)])


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('source',type=Path);parser.add_argument('output',type=Path)
    args=parser.parse_args();raw=args.source.read_bytes();source=json.loads(raw)
    try:
        result=build(source['rows']);result['status']='candidate_correspondence'
    except ValueError as error:
        result=dict(authority='none',selected=False,status='not_generated',reason=str(error),
                    tolerance_px=.1,vertex_limit=512)
    result.update(parent=source['candidate'],contour_sha256=sha256(raw).hexdigest())
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x',encoding='utf-8') as stream:json.dump(result,stream)
    print(json.dumps({k:v for k,v in result.items() if k not in ('frames','anchor_keys','span_counts','span_parameters')}))
