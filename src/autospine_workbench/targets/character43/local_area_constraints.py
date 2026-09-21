"""Small-neighborhood constrained solve after cyclic area projection stalls."""
import math


def refine(context,base,initial,*,analytic=False):
    import numpy as np
    from scipy.optimize import minimize
    triangles=np.asarray(context['row']['triangles'],dtype=int)
    refs=np.asarray(context['areas'],dtype=float)
    points=np.asarray(initial,dtype=float);origin=np.asarray(base,dtype=float)
    edges=np.asarray(context['edges'],dtype=int);lengths=np.asarray(context['lengths'],dtype=float)
    budget=context['budget']
    if (points.shape!=origin.shape or points.ndim!=2 or points.shape[1]!=2 or not np.isfinite(points).all()
            or not np.isfinite(origin).all() or not math.isfinite(budget) or budget<=0 or np.any(abs(refs)<1e-12)):
        raise ValueError('local_area_context_invalid')
    def ratios(p):
        a,b,c=(p[triangles[:,i]] for i in range(3))
        return ((b[:,0]-a[:,0])*(c[:,1]-a[:,1])-(b[:,1]-a[:,1])*(c[:,0]-a[:,0]))*.5/refs
    values=ratios(points);bad=np.flatnonzero((values<.50001)|(values>1.99999))
    touched=set(triangles[bad].flat)
    touched.update(edges[np.linalg.norm(points[edges[:,0]]-points[edges[:,1]],axis=1)>1.99999*lengths].flat)
    neighborhood=set(touched)
    for tri in triangles:
        if touched.intersection(tri):neighborhood.update(tri)
    movable=sorted(int(v) for v in neighborhood if context['free'][v])
    report=dict(profile='local-area-fixed-budget-v1',authority='none',selected=False,
                movable_vertices=movable,initial_failed_triangles=bad.tolist(),budget_px=budget)
    if analytic:report['profile']='local-area-analytic-fixed-budget-v1-experiment'
    if not movable or len(movable)>32:
        return initial,dict(report,status='local_patch_unavailable')
    indices=np.asarray(movable);size=len(indices)
    def unpack(v):
        p=points.copy();p[indices]=origin[indices]+v.reshape(size,2)*budget
        return p
    def constraints(v):
        p=unpack(v);r=ratios(p)
        distances=np.sum((p[edges[:,0]]-p[edges[:,1]])**2,axis=1)
        return np.concatenate((r-.50001,1.99999-r,
            1.99999**2-distances/np.maximum(lengths**2,1e-20),
            1-np.sum(v.reshape(size,2)**2,axis=1)))
    seed=(points[indices]-origin[indices])/budget
    seed/=np.maximum(1,np.linalg.norm(seed,axis=1))[:,None]
    seed=seed.ravel()
    best=None
    derivatives={};constraint=dict(type='ineq',fun=constraints)
    if analytic:
        from .local_area_derivatives import jacobian
        derivatives['jac']=lambda v:2*(v-seed)
        constraint['jac']=lambda v:jacobian(unpack(v),triangles,refs,edges,lengths,indices,budget,v)
    for start in (seed,np.zeros_like(seed)):
        result=minimize(lambda v:float(np.sum((v-seed)**2)),start,method='SLSQP',
            bounds=[(-1,1)]*len(seed),constraints=[constraint],**derivatives,
            options=dict(maxiter=400,ftol=1e-12))
        if not np.isfinite(result.x).all():continue
        v=result.x.reshape(size,2);v/=np.maximum(1,np.linalg.norm(v,axis=1))[:,None]
        p=unpack(v.ravel());r=ratios(p)
        valid=(min(r)>=.5 and max(r)<=2 and np.all(np.linalg.norm(p-origin,axis=1)<=budget+1e-7)
               and np.all(np.linalg.norm(p[np.logical_not(context['free'])]-origin[np.logical_not(context['free'])],axis=1)<=1e-7)
               and np.all(np.linalg.norm(p[edges[:,0]]-p[edges[:,1]],axis=1)<=2*lengths+1e-7))
        row=dict(report,status='candidate' if valid else 'no_feasible_patch_found',
                 min_ratio=float(min(r)),max_ratio=float(max(r)),iterations=int(result.nit),
                 optimizer_success=bool(result.success))
        if valid:return p.tolist(),row
        if best is None or row['min_ratio']>best['min_ratio']:best=row
    return initial,best or dict(report,status='nonfinite_optimizer_result')
