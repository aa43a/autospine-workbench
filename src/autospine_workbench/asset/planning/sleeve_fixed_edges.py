"""Necessary edge feasibility with protected endpoints at recorded poses."""
import math
from ..joints.mesh_weights import _area


def inspect(points, triangles, protected, tracks, limit=2.):
    if type(limit) not in (int,float) or not math.isfinite(limit) or limit<=0:
        raise ValueError('sleeve_fixed_edge_limit')
    def valid_point(p):
        return len(p)==2 and all(type(v) in (int,float) and math.isfinite(v) for v in p)
    if not all(valid_point(p) for p in points):raise ValueError('sleeve_fixed_edge_points')
    pins=set(protected)
    if any(type(v)!=int or not 0<=v<len(points) for v in pins):raise ValueError('sleeve_fixed_edge_pins')
    edges=set()
    for tri in triangles:
        if len(tri)!=3 or any(type(v)!=int or not 0<=v<len(points) for v in tri):
            raise ValueError('sleeve_fixed_edge_topology')
        for i,j in zip(tri,tri[1:]+tri[:1]):
            if i in pins and j in pins:edges.add(tuple(sorted((i,j))))
    lengths={edge:math.dist(points[edge[0]],points[edge[1]]) for edge in edges}
    if any(v<=1e-12 for v in lengths.values()):raise ValueError('sleeve_fixed_edge_degenerate')
    witnesses=[];peak=0.;tested=0
    for track in tracks:
        for index,sample in enumerate(track['samples']):
            current=sample['points']
            if len(current)!=len(points) or not all(valid_point(p) for p in current):
                raise ValueError('sleeve_fixed_edge_sample')
            tested+=1
            for (i,j),rest in sorted(lengths.items()):
                distance=math.dist(current[i],current[j]);ratio=distance/rest;peak=max(peak,ratio)
                if ratio>limit+1e-9:
                    witnesses.append(dict(track=track['bone_id'],sample_index=index,vertices=[i,j],
                        rest_length=rest,posed_length=distance,ratio=ratio,angles=sample.get('angles')))
    return dict(profile='protected-endpoint-edge-feasibility-v1',limit=limit,peak_ratio=peak,
        tested_poses=tested,tested_edges=len(edges),witnesses=witnesses,
        status='infeasible_with_fixed_endpoints' if witnesses else 'no_fixed_edge_counterexample',
        scope='recorded_poses_fixed_endpoints_only_not_full_mesh_feasibility',
        authority='none',production_authorized=False)


def inspect_areas(points,triangles,protected,tracks):
    """An unmovable triangle cannot be repaired by moving its neighbors."""
    checked=inspect(points,triangles,protected,tracks)
    pins=set(protected);fixed={i:t for i,t in enumerate(triangles) if set(t)<=pins}
    areas={i:_area(points,t) for i,t in fixed.items()}
    if any(abs(a)<=1e-12 for a in areas.values()):raise ValueError('sleeve_fixed_area_degenerate')
    witnesses=[];minimum=1.;maximum=1.
    for track in tracks:
        for index,sample in enumerate(track['samples']):
            for i,t in fixed.items():
                ratio=_area(sample['points'],t)/areas[i]
                minimum=min(minimum,ratio);maximum=max(maximum,ratio)
                if ratio<.5 or ratio>2:
                    witnesses.append(dict(track=track['bone_id'],sample_index=index,triangle=i,
                        vertices=list(t),ratio=ratio,angles=sample.get('angles')))
    return dict(profile='protected-triangle-area-feasibility-v1',min_ratio=minimum,max_ratio=maximum,
        tested_triangles=len(fixed),tested_poses=checked['tested_poses'],witnesses=witnesses,
        limits=[.5,2.],status='infeasible_with_fixed_vertices' if witnesses else 'no_fixed_area_counterexample',
        scope='recorded_poses_fixed_vertices_only_not_full_mesh_feasibility',authority='none',production_authorized=False)
