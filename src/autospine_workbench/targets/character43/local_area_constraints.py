"""Small-neighborhood constrained solve after cyclic area projection stalls."""
import math
from .interpolation_area_margin import targets


def refine(context,base,initial,*,analytic=False,expanded=False,recover_source=False,recover_area=False,active_tolerance=0.,feasibility_first=False):
    if feasibility_first and not analytic:raise ValueError('local_area_feasibility_requires_derivatives')
    if not math.isfinite(active_tolerance) or not 0<=active_tolerance<=1e-7:
        raise ValueError('local_area_active_tolerance_invalid')
    if expanded and not analytic:raise ValueError('expanded_area_requires_analytic_derivatives')
    if recover_area and not (analytic and recover_source):raise ValueError('area_recovery_requires_source_analytic')
    import numpy as np
    from scipy.optimize import minimize, least_squares
    triangles=np.asarray(context['row']['triangles'],dtype=int)
    refs=np.asarray(context['areas'],dtype=float)
    floors=np.asarray(targets(context))
    points=np.asarray(initial,dtype=float);origin=np.asarray(base,dtype=float)
    edges=np.asarray(context['edges'],dtype=int);lengths=np.asarray(context['lengths'],dtype=float)
    budget=context['budget']
    if (points.shape!=origin.shape or points.ndim!=2 or points.shape[1]!=2 or not np.isfinite(points).all()
            or not np.isfinite(origin).all() or not math.isfinite(budget) or budget<=0 or np.any(abs(refs)<1e-12)):
        raise ValueError('local_area_context_invalid')
    def ratios(p):
        a,b,c=(p[triangles[:,i]] for i in range(3))
        return ((b[:,0]-a[:,0])*(c[:,1]-a[:,1])-(b[:,1]-a[:,1])*(c[:,0]-a[:,0]))*.5/refs
    lower=np.maximum(.50001,floors)
    # This only selects movable neighborhoods. Final checks below are unchanged.
    values=ratios(points);bad=np.flatnonzero((values<lower-active_tolerance)|(values>1.99999))
    touched=set(triangles[bad].flat)
    if recover_source:
        # Include compressed but formally valid triangles in the local repair.
        compressed=np.flatnonzero(values<np.minimum(ratios(origin),1.)-1e-7)
        touched.update(triangles[compressed].flat)
    touched.update(edges[np.linalg.norm(points[edges[:,0]]-points[edges[:,1]],axis=1)>1.99999*lengths].flat)
    neighborhood=set(touched)
    for tri in triangles:
        if touched.intersection(tri):neighborhood.update(tri)
    movable=sorted(int(v) for v in neighborhood if context['free'][v])
    report=dict(profile='local-area-fixed-budget-v1',authority='none',selected=False,
                movable_vertices=movable,initial_failed_triangles=bad.tolist(),budget_px=budget)
    if active_tolerance:report['active_selection_tolerance']=active_tolerance
    if analytic:report['profile']='local-area-analytic-fixed-budget-v1-experiment'
    if 'minimum_ratios' in context:report['profile']='local-area-preservation-v1-experiment'
    if expanded:
        report.update(profile='expanded-area-analytic-v1-experiment',vertex_limit=128)
    if recover_source:report['profile']='source-shape-local-recovery-v1-experiment'
    if recover_area:report['profile']='source-area-local-recovery-v1-experiment'
    if not movable or len(movable)>(128 if expanded else 32):
        return initial,dict(report,status='local_patch_unavailable')
    indices=np.asarray(movable);size=len(indices)
    mask=None
    if active_tolerance:
        active_tri=np.any(np.isin(triangles,indices),axis=1)
        active_edge=np.any(np.isin(edges,indices),axis=1)
        frozen_tri=np.flatnonzero(~active_tri & ((values<.5)|(values>2)|(values<floors-1e-7)))
        frozen_edge=np.flatnonzero(~active_edge & (np.linalg.norm(points[edges[:,0]]-points[edges[:,1]],axis=1)>2*lengths+1e-7))
        if len(frozen_tri) or len(frozen_edge):
            return initial,dict(report,status='frozen_local_context_failed',
                frozen_triangles=frozen_tri.tolist(),frozen_edges=frozen_edge.tolist())
        # Valid constant inequalities cannot be improved by this local domain.
        # Remove their zero Jacobian rows; keep the full independent final check.
        mask=np.concatenate((active_tri,active_tri,active_edge,np.ones(size,dtype=bool)))
        report['validated_constant_constraints']=int(np.sum(~mask))
    def unpack(v):
        p=points.copy();p[indices]=origin[indices]+v.reshape(size,2)*budget
        return p
    def constraints(v):
        p=unpack(v);r=ratios(p)
        distances=np.sum((p[edges[:,0]]-p[edges[:,1]])**2,axis=1)
        values=np.concatenate((r-lower,1.99999-r,
            1.99999**2-distances/np.maximum(lengths**2,1e-20),
            1-np.sum(v.reshape(size,2)**2,axis=1)))
        return values if mask is None else values[mask]
    seed=(points[indices]-origin[indices])/budget
    seed/=np.maximum(1,np.linalg.norm(seed,axis=1))[:,None]
    seed=seed.ravel()
    target=np.zeros_like(seed) if recover_source else seed
    best=None
    derivatives={};constraint=dict(type='ineq',fun=constraints)
    area_target=np.minimum(1.,np.maximum(.5,ratios(origin)))
    def objective(v):
        if not recover_area:return float(np.sum((v-target)**2))
        deficit=np.minimum(0.,ratios(unpack(v))-area_target)
        return float(np.sum(deficit**2)+.001*np.sum(v*v))
    if analytic:
        from .local_area_derivatives import jacobian
        derivatives['jac']=lambda v:2*(v-target)
        full_jacobian=lambda v:jacobian(unpack(v),triangles,refs,edges,lengths,indices,budget,v)
        constraint['jac']=lambda v:full_jacobian(v) if mask is None else full_jacobian(v)[mask]
        if recover_area:
            derivatives['jac']=lambda v:2*np.minimum(0.,ratios(unpack(v))-area_target)@full_jacobian(v)[:len(triangles)]+.002*v
    def attempts(start):
        if feasibility_first:
            yield least_squares(lambda v:np.minimum(0.,constraints(v)),start,
                jac=lambda v:constraint['jac'](v)*(constraints(v)<0)[:,None],
                bounds=(-1,1),max_nfev=400,ftol=1e-14,xtol=1e-14,gtol=1e-14), 'least_squares_feasibility'
        yield minimize(objective,start,method='SLSQP',
            bounds=[(-1,1)]*len(seed),constraints=[constraint],**derivatives,
            options=dict(maxiter=400,ftol=1e-12)), 'SLSQP'
    def solutions():
        for start in (seed,np.zeros_like(seed)):
            yield from attempts(start)
    for result,method in solutions():
        if not np.isfinite(result.x).all():continue
        v=result.x.reshape(size,2);v/=np.maximum(1,np.linalg.norm(v,axis=1))[:,None]
        p=unpack(v.ravel());r=ratios(p)
        valid=(min(r)>=.5 and max(r)<=2 and np.all(np.linalg.norm(p-origin,axis=1)<=budget+1e-7)
               and np.all(np.linalg.norm(p[np.logical_not(context['free'])]-origin[np.logical_not(context['free'])],axis=1)<=1e-7)
               and np.all(np.linalg.norm(p[edges[:,0]]-p[edges[:,1]],axis=1)<=2*lengths+1e-7))
        if 'minimum_ratios' in context:valid=valid and bool(np.all(r>=floors-1e-7))
        row=dict(report,status='candidate' if valid else 'no_feasible_patch_found',
                 min_ratio=float(min(r)),max_ratio=float(max(r)),iterations=int(result.get('nit',result.get('nfev',0))),
                 optimizer_success=bool(result.success))
        row['optimizer_method']=method
        row['residuals']=dict(
            floor_deficit=float(np.max(floors-r)),
            failed_floor_triangles=np.flatnonzero(r<floors-1e-7).tolist(),
            edge_excess_px=float(np.max(np.linalg.norm(p[edges[:,0]]-p[edges[:,1]],axis=1)-2*lengths)),
            budget_excess_px=float(np.max(np.linalg.norm(p-origin,axis=1)-budget)),
            fixed_shift_px=float(np.max(np.linalg.norm(p[np.logical_not(context['free'])]-origin[np.logical_not(context['free'])],axis=1),initial=0)))
        row['optimizer_message']=str(result.message)
        if valid:return p.tolist(),row
        if best is None or row['min_ratio']>best['min_ratio']:best=row
    return initial,best or dict(report,status='nonfinite_optimizer_result')
