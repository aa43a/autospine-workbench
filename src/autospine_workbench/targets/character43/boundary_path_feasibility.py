"""Necessary fixed-boundary distance bounds across movable mesh paths."""
import heapq
import math


def inspect(setup,triangles,fixed,free,max_stretch=2.):
    if (len(setup)!=len(fixed) or not math.isfinite(max_stretch) or max_stretch<=0
            or any(len(p)!=2 or any(not math.isfinite(v) for v in p) for p in [*setup,*fixed])):
        raise ValueError('boundary_path_context')
    movable=set(free)
    if any(type(v) is not int or not 0<=v<len(setup) for v in movable):raise ValueError('boundary_path_free')
    graph=[{} for _ in setup]
    for tri in triangles:
        if len(tri)!=3 or len(set(tri))!=3 or any(type(v) is not int or not 0<=v<len(setup) for v in tri):
            raise ValueError('boundary_path_triangle')
        for a,b in zip(tri,tri[1:]+tri[:1]):
            length=math.dist(setup[a],setup[b])
            if length<=0:raise ValueError('boundary_path_degenerate')
            graph[a][b]=length;graph[b][a]=length
    witnesses=[]
    for start in range(len(setup)):
        if start in movable:continue
        distances={start:0.};previous={};queue=[(0.,start)]
        while queue:
            distance,a=heapq.heappop(queue)
            if distance>distances[a]:continue
            for b,length in graph[a].items():
                trial=distance+length
                if trial<distances.get(b,math.inf):
                    distances[b]=trial;previous[b]=a;heapq.heappush(queue,(trial,b))
        for end,distance in distances.items():
            if end<=start or end in movable:continue
            actual=math.dist(fixed[start],fixed[end]);limit=max_stretch*distance
            if actual<=limit+1e-8:continue
            path=[end]
            while path[-1]!=start:path.append(previous[path[-1]])
            witnesses.append(dict(vertices=[start,end],path=path[::-1],distance_px=actual,
                                  maximum_distance_px=limit,ratio=actual/limit))
    return dict(status='fixed_boundary_path_conflict' if witnesses else 'no_path_counterexample',
                witnesses=sorted(witnesses,key=lambda r:-r['ratio']),max_edge_stretch=max_stretch,
                scope='necessary_path_bound_not_full_mesh_feasibility')
