"""Sparse ambiguous-only space/time graph with unchanged hard depth evidence."""
from collections import defaultdict
from itertools import combinations
import json
import math
from .depth_coherent_frame import adjacency


def build(mesh,models,checks,arm):
    nodes={};unary=[];edges=[];frames={}
    for body,rows in sorted(models.items()):
        for j,row in enumerate(rows):
            if any(type(row.get(k)) not in (int,float) or not math.isfinite(row[k]) for k in ('time','source_tick')):
                raise ValueError('temporal_depth_time_invalid')
            if (len(row['labels'])!=len(mesh['triangles'])//3 or len(row['observed_states'])!=len(row['labels'])
                or any(s not in 'FBAUMN' for s in row['observed_states'])
                or any(v not in (0,1) for v in row['labels'])):raise ValueError('temporal_depth_inventory')
            if j and row['time']<=rows[j-1]['time']:raise ValueError('temporal_depth_time_order')
            frames[body,j]=row
            for i,state in enumerate(row['observed_states']):
                if state=='A':
                    if len(nodes)>=32768:raise ValueError('temporal_depth_node_limit')
                    nodes[body,j,i]=len(nodes);v=row['labels'][i]
                    unary.append([int(v!=0),int(v!=1)])
    def link(a,b):
        x,y=nodes.get(a),nodes.get(b)
        if x is not None and y is not None:edges.append((x,y,8))
        elif (x is None)!=(y is None):
            free,fixed=(x,b) if x is not None else (y,a)
            row=frames[fixed[:2]];state=row['observed_states'][fixed[2]]
            if state in 'FB':unary[free][int(state=='B')]+=8
    adjacent=adjacency(mesh)
    for (body,j),row in frames.items():
        for a,b in adjacent:link((body,j,a),(body,j,b))
        if j:
            for i in range(len(row['labels'])):link((body,j-1,i),(body,j,i))
    selected=[c for c in checks if c['arm']==arm]
    lookup={(c['body'],c['time']):c for c in selected}
    if len(lookup)!=len(selected):raise ValueError('temporal_depth_duplicate_check')
    groups=defaultdict(list)
    for (body,j),row in frames.items():
        c=lookup.get((body,row['time']),{});e=c.get('reference_plane_evidence',{})
        plane=c.get('reference_plane')
        if (isinstance(plane,list) and len(plane)==3 and all(type(v) in (int,float) and math.isfinite(v) for v in plane)
            and e.get('profile')=='torso-anchored-planar-garment-depth-v1-experiment' and
            c.get('source_tick')==row['source_tick'] and c.get('reference_plane')==e.get('coefficients')):
            groups[row['time'],json.dumps(e,sort_keys=True)].append((body,j))
    for group in groups.values():
        for a,b in combinations(group,2):
            for i in range(len(frames[a]['labels'])):
                if (*a,i) in nodes and (*b,i) in nodes:link((*a,i),(*b,i))
    if len(edges)>131072:raise ValueError('temporal_depth_edge_limit')
    return nodes,unary,edges
