"""Necessary upper-stretch reach bounds, not a complete cloth feasibility solver."""
import heapq
import math


def inspect(setup, fixed_pose, triangles, free_vertices, target, *, upper=1.4):
    n=len(setup);free=set(free_vertices)
    if (type(upper) not in (int,float) or not math.isfinite(upper) or upper<=0 or not n
            or len(fixed_pose)!=n or len(target)!=n or not free
            or any(type(i) is not int or not 0<=i<n for i in free)
            or any(len(p)!=2 or any(type(x) not in (int,float) or not math.isfinite(x) for x in p)
                   for points in (setup,fixed_pose,target) for p in points)
            or not triangles or any(len(t)!=3 or len(set(t))!=3 or
                any(type(i) is not int or not 0<=i<n for i in t) for t in triangles)):
        raise ValueError('cloth_reachability_input')
    selected=[t for t in triangles if any(i in free for i in t)]
    edges=sorted({tuple(sorted((a,b))) for t in selected for a,b in zip(t,t[1:]+t[:1])})
    graph=[{} for _ in setup]
    for a,b in edges:
        distance=math.dist(setup[a],setup[b])
        if not math.isfinite(distance):raise ValueError('cloth_reachability_nonfinite_distance')
        if distance<1e-10:raise ValueError('cloth_reachability_degenerate')
        graph[a][b]=graph[b][a]=distance
    anchors=sorted({i for t in selected for i in t}-free)
    rows={i:dict(vertex=i,anchor=None,target_gap_lower_bound_px=0.,path=[],path_length_px=None) for i in sorted(free)}
    reached=set()
    for anchor in anchors:
        distances={anchor:0.};previous={};queue=[(0.,anchor)]
        while queue:
            distance,i=heapq.heappop(queue)
            if distance!=distances[i]:continue
            for j,length in sorted(graph[i].items()):
                candidate=distance+length
                if not math.isfinite(candidate):raise ValueError('cloth_reachability_nonfinite_distance')
                if candidate<distances.get(j,float('inf')):
                    distances[j]=candidate;previous[j]=i;heapq.heappush(queue,(candidate,j))
        for i in sorted(free & distances.keys()):
            reached.add(i)
            desired=math.dist(target[i],fixed_pose[anchor]);radius=upper*distances[i]
            if not math.isfinite(desired) or not math.isfinite(radius):
                raise ValueError('cloth_reachability_nonfinite_distance')
            gap=max(0.,desired-radius)
            if rows[i]['anchor'] is None or gap>rows[i]['target_gap_lower_bound_px']:
                path=[i]
                while path[-1]!=anchor:path.append(previous[path[-1]])
                rows[i].update(anchor=anchor,target_gap_lower_bound_px=gap,
                               path=list(reversed(path)),path_length_px=distances[i])
    records=list(rows.values());unanchored=sorted(free-reached)
    bound=math.hypot(*(r['target_gap_lower_bound_px']/math.sqrt(len(records)) for r in records))
    return dict(profile='fixed-boundary-mesh-path-upper-stretch-v1',authority='none',selected=False,
                upper_stretch=upper,anchor_vertices=anchors,unanchored_vertices=unanchored,records=records,
                target_rms_lower_bound_px=bound,
                status='target_unreachable_with_fixed_boundary' if bound>1e-8 else
                    'unanchored_component' if unanchored else 'no_path_bound_counterexample',
                limitation='necessary_path_bound_only_not_global_feasibility_or_visual_acceptance')
