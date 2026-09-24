"""Necessary edge-length condition for fixed material anchors; never a pass proof."""
import heapq
import math


def inspect_paths(setup, posed, triangles, targets, movable, max_stretch=2.0):
    if not math.isfinite(max_stretch) or max_stretch <= 0:
        raise ValueError('anchor_constraint_stretch')
    graph=[{} for _ in setup]
    for tri in triangles:
        for a,b in zip(tri,tri[1:]+tri[:1]):
            length=math.dist(setup[a],setup[b])
            graph[a][b]=graph[b][a]=length
    fixed={i:p for i,p in enumerate(posed) if i not in set(movable)}
    fixed.update(targets)
    witnesses=[]; checked=set()
    for source in sorted(targets):
        distances={source:0.0}; parents={}; queue=[(0.0,source)]
        while queue:
            distance,vertex=heapq.heappop(queue)
            if distance != distances[vertex]:
                continue
            for neighbor,length in graph[vertex].items():
                candidate=distance+length
                if candidate < distances.get(neighbor,math.inf):
                    distances[neighbor]=candidate; parents[neighbor]=vertex
                    heapq.heappush(queue,(candidate,neighbor))
        for endpoint in sorted(fixed):
            pair=tuple(sorted((source,endpoint)))
            if endpoint==source or endpoint not in distances or pair in checked:
                continue
            checked.add(pair)
            required=math.dist(fixed[source],fixed[endpoint])
            limit=max_stretch*distances[endpoint]
            if required <= limit+1e-8*max(1.0,limit):
                continue
            path=[endpoint]
            while path[-1]!=source:
                path.append(parents[path[-1]])
            witnesses.append(dict(anchor=source,endpoint=endpoint,path=path[::-1],
                required_distance_px=required,maximum_path_length_px=limit,
                minimum_required_edge_stretch=required/distances[endpoint]))
    return dict(status='infeasible_fixed_anchors' if witnesses else 'no_path_counterexample',
                max_edge_stretch=max_stretch,checked_pairs=len(checked),witnesses=witnesses,
                sufficiency=False,authority='none',selected=False)
