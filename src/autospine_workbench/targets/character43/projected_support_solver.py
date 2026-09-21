"""Bounded contact feasibility with fixed projected bend directions, not adoption."""
import math


def solve(chains, reference_length, *, root_ratio=.15, length_ratio=.15):
    """A common root shift plus uniform per-chain projected length compensation.

    Both segment vectors receive the same positive factor, preserving their
    projected directions and bend sign. This does not authorize texture stretch,
    solve depth, or establish time-continuous contact.
    """
    import numpy as np
    from scipy.optimize import minimize
    if (not 1 <= len(chains) <= 2 or not math.isfinite(reference_length) or reference_length <= 0
            or not 0 < root_ratio <= .5 or not 0 < length_ratio < 1):
        raise ValueError('projected_support_limits_invalid')
    for row in chains:
        for key in ('hip','knee','ankle','target'):
            if len(row[key])!=2 or not all(math.isfinite(v) for v in row[key]):
                raise ValueError('projected_support_points_invalid')
        if math.dist(row['hip'],row['ankle']) <= 1e-8:
            raise ValueError('projected_support_collapsed_chain')
    n=len(chains)
    hips=np.array([r['hip'] for r in chains])/reference_length
    spans=(np.array([r['ankle'] for r in chains])-np.array([r['hip'] for r in chains]))/reference_length
    targets=np.array([r['target'] for r in chains])/reference_length
    def endpoints(v):return hips+v[:2]+spans*(1+v[2:,None])
    def objective(v):
        residual=endpoints(v)-targets
        return float(np.sum(residual**2)+1e-9*np.dot(v,v))
    result=minimize(objective,np.zeros(2+n),method='SLSQP',
        bounds=[(-root_ratio,root_ratio)]*2+[(-length_ratio,length_ratio)]*n,
        constraints=[dict(type='ineq',fun=lambda v:root_ratio**2-float(np.dot(v[:2],v[:2])))],
        options=dict(maxiter=300,ftol=1e-14))
    v=np.asarray(result.x)
    if not np.isfinite(v).all():raise ValueError('projected_support_nonfinite_result')
    # Recompute with exact bounded parameters, rather than trust optimizer status.
    v[2:]=np.clip(v[2:],-length_ratio,length_ratio)
    distance=float(np.linalg.norm(v[:2]))
    if distance>root_ratio:v[:2]*=root_ratio/distance
    errors=np.linalg.norm(endpoints(v)-targets,axis=1)*reference_length
    rows=[]
    for i,r in enumerate(chains):
        factor=float(1+v[2+i]);shift=v[:2]*reference_length
        hip=np.array(r['hip'])+shift
        knee=hip+(np.array(r['knee'])-np.array(r['hip']))*factor
        ankle=hip+(np.array(r['ankle'])-np.array(r['hip']))*factor
        rows.append(dict(factor=factor,hip=hip.tolist(),knee=knee.tolist(),ankle=ankle.tolist(),error_px=float(errors[i])))
    return dict(profile='fixed-bend-projected-support-v1-experiment',authority='none',selected=False,
        status='candidate' if max(errors)<=.01*reference_length else 'no_bounded_solution_found',
        root_shift=(v[:2]*reference_length).tolist(),chains=rows,solver_success=bool(result.success),
        limits=dict(root_ratio=root_ratio,length_ratio=length_ratio,residual_ratio=.01),
        limitations=['single_frame_feasibility_not_temporal_contact','length_compensation_requires_mesh_and_visual_checks'])
