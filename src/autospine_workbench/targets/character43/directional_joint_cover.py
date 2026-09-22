"""Two-axis material cover experiment with unchanged affine geometry budgets."""
import math
import numpy as np
from scipy.optimize import minimize
from scipy.spatial import ConvexHull,QhullError


def cover(points,center,targets,basis,*,padding=0.):
    p=np.asarray(points,float);c=np.asarray(center,float);q=np.asarray(targets,float);B=np.asarray(basis,float)
    if (p.ndim!=2 or p.shape[1]!=2 or len(p)<3 or q.ndim!=2 or q.shape[1]!=2 or not len(q)
            or c.shape!=(2,) or B.shape!=(2,2) or not all(np.isfinite(a).all() for a in (p,c,q,B))
            or not math.isfinite(padding) or padding<0):raise ValueError('directional_cover_input')
    det=float(np.linalg.det(B));singular=np.linalg.svd(B,compute_uv=False)
    if det<=1e-10 or det>2 or singular[0]>2:raise ValueError('directional_cover_base_geometry')
    inverse=np.linalg.inv(B);local=(p-c)@inverse.T;target=(q-c)@inverse.T
    try:hull=ConvexHull(local)
    except QhullError as exc:raise ValueError('directional_cover_degenerate') from exc
    n=hull.equations[:,:2];d=-hull.equations[:,2]
    if d.min()<=1e-8:raise ValueError('directional_cover_center_outside')
    bound=float(2/singular[-1])
    if bound>100:raise ValueError('directional_cover_near_singular')
    def constraints(scale):
        # Transform each local half-plane normal into world space so padding
        # remains in pixels even under anisotropic scale.
        padding_local=padding*np.linalg.norm((n/scale)@inverse,axis=1)
        gaps=d-(target/scale)@n.T-padding_local
        return np.r_[gaps.flatten(),2-det*np.prod(scale),2-np.linalg.svd(B@np.diag(scale),compute_uv=False)[0]]
    starts=[[1,1],[min(bound,math.sqrt(2/det))]*2,[bound,1],[1,bound]]
    best=None;attempts=[]
    for start in starts:
        fit=minimize(lambda x:float(np.log(x)@np.log(x)),start,bounds=[(1,bound)]*2,
            method='SLSQP',constraints=[dict(type='ineq',fun=lambda x:constraints(x)-1e-8)],
            options=dict(maxiter=100,ftol=1e-10))
        residual=float(constraints(fit.x).min())
        valid=np.isfinite(fit.x).all() and residual>=0
        attempts.append(dict(success=bool(fit.success),minimum_constraint=residual,iterations=int(fit.nit)))
        if valid and (best is None or fit.fun<best.fun):best=fit
    scales=best.x if best is not None else np.ones(2)
    result=c+(local*scales)@B.T
    return result.tolist(),dict(status='bounded_directional_cover' if best is not None else 'no_feasible_directional_cover',
        applied_scales=scales.tolist(),determinant=det*float(np.prod(scales)),
        maximum_stretch=float(np.linalg.svd(B@np.diag(scales),compute_uv=False)[0]),
        minimum_constraint=float(constraints(scales).min()),attempts=attempts,
        scope='sampled_convex_geometry_not_alpha_or_global_infeasibility_proof',selected=False)
