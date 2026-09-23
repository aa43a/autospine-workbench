"""Experimental one-band boundary transport; no claim of shape feasibility."""
from copy import deepcopy
import heapq
import math
from statistics import median
from .affine_pose import matrices,sample
from .deform_addition import entries,local_delta,add


def blend(document,name,slot,partition,setup,times):
    result=deepcopy(document);mesh=document['skins'][0]['attachments'][slot][slot]
    pairs=partition['boundary_pairs'];selected=set(partition['duplicated_vertices'].values())
    if not pairs:raise ValueError('partition_boundary_missing')
    triangles=[mesh['triangles'][i:i+3] for i in range(0,len(mesh['triangles']),3)]
    edges={tuple(sorted((t[i],t[(i+1)%3]))) for t in triangles for i in range(3) if all(v in selected for v in t)}
    graph={v:[] for v in selected};lengths=[]
    for a,b in edges:
        length=math.dist(setup[a],setup[b]);lengths.append(length);graph[a].append((b,length));graph[b].append((a,length))
    if not lengths or min(lengths)<=1e-10:raise ValueError('partition_boundary_bad_edges')
    width=2*median(lengths);distance={v:math.inf for v in selected};driver={};queue=[]
    for source,target in pairs:distance[target]=0;driver[target]=source;heapq.heappush(queue,(0,target))
    while queue:
        d,v=heapq.heappop(queue)
        if d!=distance[v]:continue
        for other,length in graph[v]:
            if d+length<distance[other]:
                distance[other]=d+length;driver[other]=driver[v];heapq.heappush(queue,(d+length,other))
    influences=entries(mesh);keys=[];rows=[]
    boundary_map={source:target for source,target in pairs}
    for time in times:
        points=sample(document,name,time)[0][slot];corrected=deepcopy(points)
        for v in selected:
            if distance[v]>=width:continue
            source=driver[v];target=boundary_map[source];q=1-distance[v]/width;weight=q*q*(3-2*q)
            corrected[v]=[points[v][k]+weight*(points[source][k]-points[target][k]) for k in (0,1)]
        keys.append(dict(time=time,vertices=local_delta(document,influences,matrices(document,name,time),points,corrected)))
        rows.append(dict(time=time,max_displacement_px=max(math.dist(a,b) for a,b in zip(points,corrected)),
            boundary_gap_px=max(math.dist(corrected[a],corrected[b]) for a,b in pairs)))
    tracks=result['animations'][name].setdefault('attachments',{}).setdefault('default',{}).setdefault(slot,{}).setdefault(slot,{})
    tracks['deform']=add(tracks.get('deform',[]),keys,2*sum(len(row) for row in influences))
    return result,dict(profile='partition-two-edge-boundary-transport-v1-experiment',band_width_px=width,rows=rows,
        authority='none',selected=False,scope='sampled_boundary_coincidence_not_shape_or_raster_acceptance')
