"""Bounded hard-constraint refinement; failure never authorizes a shape change."""
import math
from ...asset.planning.component_local_solver import metrics


def refine(setup,triangles,fixed,free,source,seed,budget,*,regions=None,region_margin=1e-5):
    import numpy as np
    from scipy.optimize import minimize
    arrays=[np.asarray(p,dtype=float) for p in (setup,fixed,source,seed)]
    if (any(p.shape!=arrays[0].shape or p.ndim!=2 or p.shape[1]!=2 or not np.isfinite(p).all() for p in arrays)
            or not 0<len(free)<=256 or len(set(free))!=len(free)
            or any(type(v) is not int or not 0<=v<len(setup) for v in free)
            or not math.isfinite(budget) or budget<=0):
        raise ValueError('boundary_feasibility_context')
    rest,locked,origin,start=arrays
    if any(len(t)!=3 or len(set(t))!=3 or any(type(v) is not int for v in t) for t in triangles):
        raise ValueError('boundary_feasibility_triangles')
    tri=np.asarray(triangles,dtype=int)
    if tri.ndim!=2 or tri.shape[1]!=3 or not len(tri) or tri.min()<0 or tri.max()>=len(setup):
        raise ValueError('boundary_feasibility_triangles')
    edges=np.asarray(sorted({tuple(sorted((a,b))) for t in triangles for a,b in zip(t,t[1:]+t[:1])}))
    def areas(p):
        a=p[tri[:,1]]-p[tri[:,0]];b=p[tri[:,2]]-p[tri[:,0]]
        return .5*(a[:,0]*b[:,1]-a[:,1]*b[:,0])
    refs=areas(rest);lengths=np.linalg.norm(rest[edges[:,0]]-rest[edges[:,1]],axis=1)
    if np.any(abs(refs)<1e-10) or np.any(lengths<=1e-10):raise ValueError('boundary_feasibility_degenerate')
    scale=float(np.median(lengths));free=list(free)
    regions=[] if regions is None else regions
    if not math.isfinite(region_margin) or not 0<region_margin<=.05:raise ValueError('boundary_feasibility_region_margin')
    for r in regions:
        if (r['vertex'] not in free or np.asarray(r['center']).shape!=(2,) or np.asarray(r['inverse']).shape!=(2,2)
                or not np.isfinite([*r['center'],*np.asarray(r['inverse']).ravel(),r['radius']]).all()
                or r['radius']<=0 or abs(np.linalg.det(r['inverse']))<1e-10):
            raise ValueError('boundary_feasibility_region')
    movable=np.zeros(len(rest),dtype=bool);movable[free]=True
    fixed_tri=~movable[tri].any(axis=1);fixed_edges=~movable[edges].any(axis=1)
    ratio=areas(locked)/refs;stretch=np.linalg.norm(locked[edges[:,0]]-locked[edges[:,1]],axis=1)/lengths
    report=dict(profile='boundary-hard-shape-feasibility-v1',authority='none',selected=False,
                scope='single_pose_not_temporal_or_visual_acceptance')
    if (np.any((ratio[fixed_tri]<.5)|(ratio[fixed_tri]>2)) or np.any(stretch[fixed_edges]>2)
            or np.any(np.linalg.norm(locked[~movable]-origin[~movable],axis=1)>budget)):
        return seed,dict(report,status='fixed_constraint_conflict')
    def unpack(x):
        p=locked.copy();p[free]=start[free]+scale*x.reshape(-1,2);return p
    def constraints(x):
        p=unpack(x);r=areas(p)/refs;s=np.linalg.norm(p[edges[:,0]]-p[edges[:,1]],axis=1)/lengths
        contact=[1-region_margin-np.linalg.norm(np.asarray(z['inverse'])@(p[z['vertex']]-z['center']))/z['radius'] for z in regions]
        return np.concatenate((r[~fixed_tri]-.505,1.995-r[~fixed_tri],1.995-s[~fixed_edges],
                               1-np.linalg.norm(p[free]-origin[free],axis=1)/budget,contact))
    fit=minimize(lambda x:float(x@x),np.zeros(2*len(free)),jac=lambda x:2*x,
                 method='SLSQP',constraints=[dict(type='ineq',fun=constraints)],
                 options=dict(maxiter=200,ftol=1e-10))
    # Only the new region experiment tolerates numerical error in the stricter
    # solver margins. Independently enforce the original geometry/budget and
    # exact contact-region bounds below; no acceptance threshold is loosened.
    finite=np.isfinite(fit.x).all();valid=finite and float(constraints(fit.x).min())>=(-1e-7 if regions else 0)
    result=unpack(fit.x) if finite else start
    quality=metrics(setup,result.tolist(),triangles)
    valid=valid and not quality['bad_triangles'] and quality['max_edge_stretch']<=2
    contact_ratios=[float(np.linalg.norm(np.asarray(z['inverse'])@(result[z['vertex']]-z['center']))/z['radius']) for z in regions]
    if regions:valid=valid and max(contact_ratios)<=1 and float(np.linalg.norm(result-origin,axis=1).max())<=budget
    report.update(status='feasible_candidate' if valid else 'no_feasible_candidate_found',
                  contact_region_count=len(regions),
                  maximum_contact_region_ratio=max(contact_ratios,default=None),
                  optimizer_success=bool(fit.success),iterations=int(fit.nit),geometry=quality,
                  minimum_constraint=float(constraints(fit.x).min()) if finite else None,
                  maximum_displacement_px=float(np.linalg.norm(result-origin,axis=1).max()))
    return result.tolist() if valid else seed,report
