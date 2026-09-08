"""Local displacement/tangent least squares with sampled geometry backtracking."""
import math
from .alpha_seam import position
from .continuous_pose import area


def admissible(vertices,moves,triangles):
    points=[[p[k]+d[k] for k in (0,1)] for p,d in zip(vertices,moves)]
    if any(not math.isfinite(v) for p in points for v in p):return False
    for tri in triangles:
        before=area(vertices,tri)
        if abs(before)<1e-12:raise ValueError('shape_degenerate_triangle')
        ratio=area(points,tri)/before
        if not .5<=ratio<=2.:return False
    edges={tuple(sorted((tri[i],tri[(i+1)%3]))) for tri in triangles for i in range(3)}
    return all(math.dist(points[a],points[b])<=2*math.dist(vertices[a],vertices[b]) for a,b in edges)


def solve(vertices,anchors,targets,triangles,chains):
    import numpy as np
    if not anchors or len(anchors)!=len(targets):raise ValueError('shape_anchor_count')
    contact=[position(a,vertices) for a in anchors];n=len(vertices)
    mobility=np.array([max(0.,1-min(math.dist(p,c) for c in contact)/48)**2 for p in vertices])
    matrix=np.zeros((len(anchors),n));target=np.asarray(targets,dtype=float)
    if target.shape!=(len(anchors),2) or not np.isfinite(target).all():raise ValueError('shape_target_nonfinite')
    for row,a in enumerate(anchors):
        for i,w in zip(a['triangle'],a['barycentric']):matrix[row,i]+=w*mobility[i]
    equations=[matrix];rhs=[target];tangent_count=0
    for chain in chains:
        for left,right in zip(chain,chain[1:]):
            if not 0<=left<len(anchors) or not 0<=right<len(anchors):raise ValueError('shape_chain_reference')
            factor=math.sqrt(2.)/max(1.,math.dist(contact[left],contact[right]))
            equations.append((matrix[right]-matrix[left])[None,:]*factor)
            rhs.append((target[right]-target[left])[None,:]*factor);tangent_count+=1
    edges=sorted({tuple(sorted((tri[i],tri[(i+1)%3]))) for tri in triangles for i in range(3)})
    smooth=np.zeros((len(edges),n))
    for row,(a,b) in enumerate(edges):smooth[row,a]=mobility[a]*math.sqrt(.08);smooth[row,b]=-mobility[b]*math.sqrt(.08)
    equations.extend([smooth,np.eye(n)*.1]);rhs.extend([np.zeros((len(edges),2)),np.zeros((n,2))])
    displacement=np.linalg.lstsq(np.vstack(equations),np.vstack(rhs),rcond=None)[0]*mobility[:,None]
    if not np.isfinite(displacement).all():raise ValueError('shape_nonfinite_solution')
    maximum=float(np.linalg.norm(displacement,axis=1).max());cap=min(1.,12/maximum) if maximum else 1.
    for step in range(13):
        scale=cap*2**(-step);moves=(displacement*scale).tolist()
        if admissible(vertices,moves,triangles):break
    else:
        moves=[[0.,0.] for _ in vertices];scale=0.;step=13
    residual=np.asarray([position(a,moves) for a in anchors])-target
    return moves,{'tangent_constraints':tangent_count,'scale':scale,'backtracks':step,
                  'max_anchor_residual_px':float(np.linalg.norm(residual,axis=1).max()),
                  'status':'candidate' if scale else 'blocked_no_admissible_step'}
