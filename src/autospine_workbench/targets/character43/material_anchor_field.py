"""Harmonic displacement from explicit material anchors, not semantic inference."""
import math
import numpy as np


def solve(setup, posed, triangles, targets, movable):
    rest, points = np.asarray(setup, float), np.asarray(posed, float)
    if rest.shape != points.shape or rest.ndim != 2 or rest.shape[1] != 2 or not np.isfinite([rest,points]).all():
        raise ValueError('anchor_field_points')
    count=len(rest); moving=set(movable)
    if (not targets or len(moving)!=len(movable) or not set(targets)<=moving or
            any(type(i) is not int or not 0<=i<count for i in moving) or len(moving)>256):
        raise ValueError('anchor_field_selection')
    adjacency=[{} for _ in rest]
    for triangle in triangles:
        if len(triangle)!=3 or len(set(triangle))!=3 or any(type(i) is not int or not 0<=i<count for i in triangle):
            raise ValueError('anchor_field_triangles')
        for a,b in zip(triangle,triangle[1:]+triangle[:1]):
            length=math.dist(rest[a],rest[b])
            if length<=1e-10: raise ValueError('anchor_field_degenerate_edge')
            adjacency[a][b]=adjacency[b][a]=1/length
    offsets=np.zeros_like(points)
    for i,target in targets.items():
        if len(target)!=2 or not np.isfinite(target).all():raise ValueError('anchor_field_target')
        offsets[i]=np.asarray(target)-points[i]
    free=sorted(moving-set(targets)); indices={v:i for i,v in enumerate(free)}
    # Each free connected component must reach a fixed anchor or exterior point.
    unseen=set(free)
    while unseen:
        stack=[unseen.pop()]; fixed=False
        while stack:
            vertex=stack.pop()
            for neighbor in adjacency[vertex]:
                if neighbor not in indices: fixed=True
                elif neighbor in unseen: unseen.remove(neighbor);stack.append(neighbor)
        if not fixed:raise ValueError('anchor_field_unconstrained_component')
    matrix=np.zeros((len(free),len(free))); rhs=np.zeros((len(free),2))
    for vertex,row in indices.items():
        for neighbor,weight in adjacency[vertex].items():
            matrix[row,row]+=weight
            if neighbor in indices: matrix[row,indices[neighbor]]-=weight
            else: rhs[row]+=weight*offsets[neighbor]
    if free: offsets[free]=np.linalg.solve(matrix,rhs)
    result=points+offsets
    if not np.isfinite(result).all():raise ValueError('anchor_field_nonfinite_result')
    return result.tolist(),dict(anchors=len(targets),free_vertices=len(free),
        maximum_displacement_px=float(np.linalg.norm(offsets,axis=1).max()),
        maximum_anchor_error_px=max(math.dist(result[i],p) for i,p in targets.items()),
        authority='none',selected=False,geometry_status='not_evaluated')
