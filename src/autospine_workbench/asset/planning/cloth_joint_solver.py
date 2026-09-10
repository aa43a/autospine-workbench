"""Optional sparse joint area/edge constraints; bounded candidate, never approval."""
from .cloth_anchor_solver import solve as project
from .component_local_solver import metrics
from .component_temporal_qa import passed


def solve(setup,triangles,points,cloth_vertices,anchors,budget,*,seed=None):
    import numpy as np
    import scipy
    from scipy.optimize import least_squares
    from scipy.sparse import lil_matrix
    initial,evidence=project(setup,triangles,points,cloth_vertices,anchors,budget,seed=seed)
    evidence.update(profile='joint-area-edge-sparse200-v1',numpy_version=np.__version__,scipy_version=scipy.__version__)
    free=sorted(set(cloth_vertices)-set(anchors))
    if not free or passed(evidence['qa']):
        evidence['solver_status']='projection_sufficient';return initial,evidence
    fixed=np.asarray(points,dtype=float);rest=np.asarray(setup,dtype=float);tri=np.asarray(triangles,dtype=int)
    edges=np.asarray(sorted({tuple(sorted((a,b))) for t in triangles for a,b in zip(t,t[1:]+t[:1])}),dtype=int)
    def area(p):
        a=p[tri[:,1]]-p[tri[:,0]];b=p[tri[:,2]]-p[tri[:,0]]
        return (a[:,0]*b[:,1]-a[:,1]*b[:,0])*.5
    areas=area(rest);lengths=np.sum((rest[edges[:,0]]-rest[edges[:,1]])**2,axis=1)
    n=len(free);nt=len(tri);ne=len(edges);lookup={v:i for i,v in enumerate(free)}
    sparsity=lil_matrix((2*nt+ne+3*n,2*n),dtype=int)
    for i,t in enumerate(tri):
        for v in t:
            if v in lookup:
                j=2*lookup[v];sparsity[i,j:j+2]=1;sparsity[nt+i,j:j+2]=1
    for i,edge in enumerate(edges):
        for v in edge:
            if v in lookup:sparsity[2*nt+i,2*lookup[v]:2*lookup[v]+2]=1
    offset=2*nt+ne
    for i in range(n):
        sparsity[offset+i,2*i:2*i+2]=1
        sparsity[offset+n+2*i,2*i]=1;sparsity[offset+n+2*i+1,2*i+1]=1
    def residual(x):
        delta=x.reshape(n,2);p=fixed.copy();p[free]+=delta*budget
        ratios=area(p)/areas;stretch=np.sum((p[edges[:,0]]-p[edges[:,1]])**2,axis=1)/lengths
        return np.concatenate((np.maximum(.55-ratios,0),np.maximum(ratios-1.9,0),
            np.maximum(stretch-1.9**2,0),10*np.maximum(np.sum(delta**2,axis=1)-1,0),.001*x))
    x0=(np.asarray(initial)[free]-fixed[free]).ravel()/budget
    fit=least_squares(residual,np.clip(x0,-1,1),bounds=(-1,1),jac_sparsity=sparsity.tocsr(),
        method='trf',max_nfev=200,ftol=1e-9,xtol=1e-9,gtol=1e-9)
    delta=fit.x.reshape(n,2);delta/=np.maximum(1,np.linalg.norm(delta,axis=1))[:,None]
    result=fixed.copy();result[free]+=budget*delta
    if not np.isfinite(result).all():raise ValueError('cloth_joint_nonfinite')
    result=result.tolist();evidence.update(qa=metrics(setup,result,triangles),solver_status=int(fit.status),evaluations=int(fit.nfev),
        max_offset=float(np.max(np.linalg.norm(delta,axis=1))*budget))
    return result,evidence
