"""Bounded multi-triangle material support; no inferred clothing ownership."""
import math
import numpy as np
from scipy.optimize import linear_sum_assignment,minimize


def candidates(mesh,points,texture,query,*,radius=8.,pixels=8):
    if (not math.isfinite(radius) or not 0<radius<=8 or type(pixels) is not int or not 1<=pixels<=8):
        raise ValueError('regional_support_budget')
    points=np.asarray(points,float);query=np.asarray(query,float)
    uv=np.asarray(mesh['uvs'],float).reshape(-1,2)
    if points.shape!=uv.shape or query.shape!=(2,) or not np.isfinite(points).all() or not np.isfinite(query).all():
        raise ValueError('regional_support_points')
    result={}
    for index,ids in enumerate(np.asarray(mesh['triangles']).reshape(-1,3)):
        tri=points[ids];distance=np.maximum(np.maximum(tri.min(axis=0)-query,query-tri.max(axis=0)),0)
        if np.linalg.norm(distance)>radius:continue
        a,b,c=tri;matrix=np.column_stack((b-a,c-a))
        if abs(np.linalg.det(matrix))<1e-12:continue
        w=np.linalg.solve(matrix,query-a);w=np.r_[1-w.sum(),w]
        if min(w)<0:
            options=[]
            for j,k in ((0,1),(1,2),(2,0)):
                d=tri[k]-tri[j];u=float(np.clip((query-tri[j])@d/(d@d),0,1))
                weights=np.zeros(3);weights[j]=1-u;weights[k]=u
                options.append((float(np.linalg.norm(weights@tri-query)),weights))
            _,w=min(options,key=lambda item:item[0])
        if np.linalg.norm(w@tri-query)>radius:continue
        ua,ub,uc=uv[ids];basis=np.column_stack((ub-ua,uc-ua))
        if abs(np.linalg.det(basis))<1e-12:continue
        center=w@uv[ids];cx,cy=int(center[0]*texture.width),int(center[1]*texture.height)
        for y in range(max(1,cy-pixels),min(texture.height-1,cy+pixels+1)):
            for x in range(max(1,cx-pixels),min(texture.width-1,cx+pixels+1)):
                if min(texture.getpixel((x+dx,y+dy))[3] for dx in (-1,0,1) for dy in (-1,0,1))<128:continue
                material=np.asarray([(x+.5)/texture.width,(y+.5)/texture.height])
                weights=np.linalg.solve(basis,material-ua);weights=np.r_[1-weights.sum(),weights]
                if min(weights)<-1e-8:continue
                world=weights@tri;dist=float(np.linalg.norm(world-query))
                if dist>radius:continue
                row=dict(triangle=index,vertices=ids.tolist(),weights=weights.tolist(),pixel=[x,y],
                         world=world.tolist(),distance_px=dist)
                key=(x,y)
                if key not in result or dist<result[key]['distance_px']:result[key]=row
    return sorted(result.values(),key=lambda r:(r['distance_px'],r['pixel'],r['triangle']))


def assign(groups):
    """Distinct opaque texels prevent unrelated targets collapsing to one material point."""
    if not groups or any(not g for g in groups):raise ValueError('regional_support_missing')
    pixels=sorted({tuple(r['pixel']) for g in groups for r in g});lookup={p:i for i,p in enumerate(pixels)}
    cost=np.full((len(groups),len(pixels)),1e12)
    for i,group in enumerate(groups):
        for row in group:cost[i,lookup[tuple(row['pixel'])]]=row['distance_px']**2
    rows,columns=linear_sum_assignment(cost)
    if len(rows)!=len(groups) or any(cost[i,j]>=1e12 for i,j in zip(rows,columns)):
        raise ValueError('regional_support_assignment_conflict')
    return [next(r for r in groups[i] if tuple(r['pixel'])==pixels[j]) for i,j in zip(rows,columns)]


def solve(rest,posed,triangles,supports,queries,fixed,*,rings=3,budget=8.,exact=(),geometry=False):
    """Least-squares material targets with harmonic regularization; output must pass independent QA."""
    rest=np.asarray(rest,float);posed=np.asarray(posed,float);queries=np.asarray(queries,float)
    if (not supports or queries.shape!=(len(supports),2) or rest.shape!=posed.shape or
        not np.isfinite(queries).all() or not np.isfinite(rest).all() or not np.isfinite(posed).all() or
        type(rings) is not int or not 0<=rings<=3 or not 0<budget<=8):
        raise ValueError('regional_support_solve_input')
    if len(set(exact))!=len(exact) or any(type(i) is not int or not 0<=i<len(supports) for i in exact):
        raise ValueError('regional_support_exact_targets')
    moving={v for s in supports for v in s['vertices']};fixed=set(fixed)
    for _ in range(rings):moving|={v for tri in triangles if moving&set(tri) for v in tri}
    moving=sorted(moving-fixed)
    if not moving or len(moving)>256:raise ValueError('regional_support_movable_budget')
    index={v:i for i,v in enumerate(moving)};edges=set()
    for tri in triangles:
        for a,b in zip(tri,tri[1:]+tri[:1]):edges.add(tuple(sorted((a,b))))
    constraints=np.zeros((len(supports),len(moving)));delta=[]
    for i,(s,q) in enumerate(zip(supports,queries,strict=True)):
        w=np.asarray(s['weights']);ids=s['vertices'];delta.append(q-w@posed[ids])
        for v,weight in zip(ids,w):
            if v in index:constraints[i,index[v]]+=weight
    smooth=[]
    for a,b in sorted(edges):
        if a not in index and b not in index:continue
        row=np.zeros(len(moving));length=float(np.linalg.norm(rest[a]-rest[b]))
        if length<=1e-10:raise ValueError('regional_support_degenerate_edge')
        if a in index:row[index[a]]=1/math.sqrt(length)
        if b in index:row[index[b]]=-1/math.sqrt(length)
        smooth.append(row)
    matrix=np.vstack((constraints*100,np.asarray(smooth),np.eye(len(moving))*1e-6))
    rhs=np.vstack((np.asarray(delta)*100,np.zeros((len(smooth)+len(moving),2))))
    offsets=np.linalg.lstsq(matrix,rhs,rcond=None)[0]
    unconstrained=float(np.linalg.norm(offsets,axis=1).max())
    optimizer='unconstrained_within_budget'
    if unconstrained>budget or exact or geometry:
        # Joint bounded least squares, not global scaling of the solved displacement.
        gram=matrix.T@matrix;linear=matrix.T@rhs;normal=max(float(np.linalg.norm(gram,2)),1.)
        def objective(x):
            p=x.reshape(-1,2);residual=matrix@p-rhs/budget
            return float(np.sum(residual*residual)/normal),(2*(gram@p-linear/budget)/normal).ravel()
        def limits(x):return (1-1e-8)**2-np.sum(x.reshape(-1,2)**2,axis=1)
        def derivative(x):
            p=x.reshape(-1,2);jac=np.zeros((len(moving),len(x)))
            for i,v in enumerate(p):jac[i,2*i:2*i+2]=-2*v
            return jac
        seed=offsets/np.maximum(np.linalg.norm(offsets,axis=1,keepdims=True),budget)
        guards=[dict(type='ineq',fun=limits,jac=derivative)]
        if geometry:
            from .regional_patch_geometry import constraints as geometry_constraints
            guards.append(geometry_constraints(rest,posed,triangles,moving,budget))
        if exact:
            exact_matrix=constraints[list(exact)];exact_rhs=np.asarray(delta)[list(exact)]/budget
            guards.append(dict(type='eq',fun=lambda x:(exact_matrix@x.reshape(-1,2)-exact_rhs).ravel(),
                               jac=lambda x:np.kron(exact_matrix,np.eye(2))))
        fit=minimize(objective,seed.ravel(),jac=True,method='SLSQP',
            constraints=guards,options=dict(maxiter=300,ftol=1e-10))
        offsets=fit.x.reshape(-1,2)*budget;optimizer='bounded_converged' if fit.success else 'bounded_failed'
    maximum=float(np.linalg.norm(offsets,axis=1).max())
    report=dict(maximum_displacement_px=maximum,movable_vertices=moving,
        unconstrained_maximum_displacement_px=unconstrained,optimizer=optimizer,
        geometry_constraints=geometry,
        maximum_target_error_px=float(np.linalg.norm(constraints@offsets-delta,axis=1).max()),
        exact_targets=list(exact),exact_target_error_px=max((float(np.linalg.norm((constraints@offsets-delta)[i])) for i in exact),default=0.),
        within_displacement_budget=maximum<=budget,authority='none',selected=False,
        scope='joint_material_targets_not_geometry_or_coverage_acceptance')
    if maximum>budget or optimizer=='bounded_failed' or report['exact_target_error_px']>1e-7:return None,report
    result=posed.copy();result[moving]+=offsets
    return result.tolist(),report
