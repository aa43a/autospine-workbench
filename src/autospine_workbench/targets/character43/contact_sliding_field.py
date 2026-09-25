"""Bounded directional contact solve from explicit guides, not inferred seams."""
import math
import numpy as np
from ...asset.planning.component_local_solver import metrics


def solve(setup, posed, triangles, fixed, sliding, preserved=()):
    """Keep all unspecified vertices unchanged; sliding guides have finite limits.

    A guide is {origin: [x,y], tangent: [x,y], limits: [min,max]} in world pixels.
    Guides must be supplied by a validated contact mapping. This routine neither
    extracts garment boundaries nor treats every mesh edge as a clothing seam.
    """
    from scipy.optimize import lsq_linear
    rest, points=np.asarray(setup,float),np.asarray(posed,float)
    if rest.ndim!=2 or rest.shape[1]!=2 or points.shape!=rest.shape or not np.isfinite([rest,points]).all():
        raise ValueError('contact_field_points_invalid')
    count=len(rest); chosen=set(fixed)|set(sliding); keep=set(preserved)
    if (not chosen or len(chosen)>256 or
            any(type(v) is not int or not 0<=v<count for v in chosen|keep)):
        raise ValueError('contact_field_selection_invalid')
    base=points.copy(); targets={}; guides={}
    for v,p in fixed.items():
        p=np.asarray(p,float)
        if p.shape!=(2,) or not np.isfinite(p).all():raise ValueError('contact_field_target_invalid')
        if v in keep and np.linalg.norm(p-points[v])>1e-6:raise ValueError('contact_field_preserved_conflict')
        targets[v]=p;base[v]=p
    for v,g in sliding.items():
        if set(g)!={'origin','tangent','limits'}:raise ValueError('contact_field_guide_invalid')
        p,t,limits=[np.asarray(g[k],float) for k in ('origin','tangent','limits')]
        if (p.shape!=(2,) or t.shape!=(2,) or limits.shape!=(2,) or not np.isfinite([p,t,limits]).all()
                or np.linalg.norm(t)<=1e-10 or limits[0]>=limits[1]):
            raise ValueError('contact_field_guide_invalid')
        t=t/np.linalg.norm(t)
        if v in fixed or v in keep:
            q=targets.get(v,points[v]); amount=float((q-p)@t)
            if np.linalg.norm(q-p-amount*t)>1e-6 or not limits[0]-1e-6<=amount<=limits[1]+1e-6:
                raise ValueError('contact_field_shared_guide_conflict')
        else:
            guides[v]=(p,t,limits);base[v]=p
    edges=set()
    for tri in triangles:
        if len(tri)!=3 or len(set(tri))!=3 or any(type(v) is not int or not 0<=v<count for v in tri):
            raise ValueError('contact_field_triangles_invalid')
        edges.update(tuple(sorted((a,b))) for a,b in zip(tri,tri[1:]+tri[:1]))
    ids=sorted(guides); index={v:i for i,v in enumerate(ids)}
    matrix=np.zeros((2*len(edges),len(ids))); rhs=np.zeros(2*len(edges))
    for i,(a,b) in enumerate(sorted(edges)):
        length=math.dist(rest[a],rest[b])
        if length<=1e-10:raise ValueError('contact_field_degenerate_edge')
        scale=1/math.sqrt(length)
        rhs[2*i:2*i+2]=-scale*((base[a]-base[b])-(points[a]-points[b]))
        for v,sign in ((a,1),(b,-1)):
            if v in index:matrix[2*i:2*i+2,index[v]]=scale*sign*guides[v][1]
    if ids:
        if np.linalg.matrix_rank(matrix)<len(ids):raise ValueError('contact_field_underdetermined')
        lower=[guides[v][2][0] for v in ids];upper=[guides[v][2][1] for v in ids]
        result=lsq_linear(matrix,rhs,bounds=(lower,upper),method='bvls',tol=1e-9,max_iter=100)
        if not result.success or not np.isfinite(result.x).all():raise ValueError('contact_field_not_converged')
        for v,amount in zip(ids,result.x):base[v]=guides[v][0]+amount*guides[v][1]
    else:
        result=None
    if not np.isfinite(base).all():raise ValueError('contact_field_nonfinite_result')
    unchanged=set(range(count))-chosen | keep
    if any(np.linalg.norm(base[v]-points[v])>1e-6 for v in unchanged):
        raise ValueError('contact_field_preservation_failed')
    guide_error=0.
    for v,g in sliding.items():
        tangent=np.asarray(g['tangent'],float);tangent/=np.linalg.norm(tangent)
        delta=base[v]-g['origin'];amount=float(delta@tangent)
        guide_error=max(guide_error,float(np.linalg.norm(delta-amount*tangent)),
                        max(0.,g['limits'][0]-amount,amount-g['limits'][1]))
    fixed_error=max((float(np.linalg.norm(base[v]-p)) for v,p in targets.items()),default=0.)
    if max(guide_error,fixed_error)>1e-6:raise ValueError('contact_field_constraint_residual')
    before=metrics(rest.tolist(),points.tolist(),triangles)
    after=metrics(rest.tolist(),base.tolist(),triangles)
    failed=bool(after['bad_triangles'] or after['inversions'] or after['max_edge_stretch']>2)
    return base.tolist(),dict(profile='bounded-directional-contact-field-v1',selected=False,authority='none',
        status='rejected_geometry' if failed else 'single_pose_requires_validation',before=before,after=after,
        fixed_vertices=len(fixed),sliding_variables=len(ids),preserved_vertices=len(unchanged),
        maximum_guide_error_px=guide_error,maximum_fixed_error_px=fixed_error,
        iterations=0 if result is None else int(result.nit),
        maximum_displacement_px=float(np.linalg.norm(base-points,axis=1).max()),
        scope='explicit_guides_single_pose_not_boundary_inference_or_runtime_validation')
