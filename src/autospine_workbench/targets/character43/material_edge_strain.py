"""Dimensionless source-edge strain and its analytic position gradient."""
import numpy as np


def energy(points, edges, lengths):
    p=np.asarray(points,float);edges=np.asarray(edges,int);lengths=np.asarray(lengths,float)
    if (p.ndim!=2 or p.shape[1]!=2 or edges.ndim!=2 or edges.shape[1]!=2 or not len(edges)
            or lengths.shape!=(len(edges),) or not np.isfinite(p).all() or not np.isfinite(lengths).all()
            or np.any(lengths<=0) or edges.min()<0 or edges.max()>=len(p)):
        raise ValueError('material_edge_strain_input')
    delta=p[edges[:,0]]-p[edges[:,1]];current=np.linalg.norm(delta,axis=1)
    if np.any(current<=1e-12):raise ValueError('material_edge_strain_collapsed')
    residual=current/lengths-1;loss=float(np.mean(residual**2));gradient=np.zeros_like(p)
    contribution=2/len(edges)*(residual/(lengths*current))[:,None]*delta
    np.add.at(gradient,edges[:,0],contribution);np.add.at(gradient,edges[:,1],-contribution)
    return loss,gradient
