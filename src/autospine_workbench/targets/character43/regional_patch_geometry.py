"""Area and edge inequalities for bounded regional material optimization."""
import numpy as np


def constraints(rest,posed,triangles,moving,budget):
    rest=np.asarray(rest,float);posed=np.asarray(posed,float);tri=np.asarray(triangles,int)
    edges=np.asarray(sorted({tuple(sorted((a,b))) for t in triangles for a,b in zip(t,t[1:]+t[:1])}))
    def areas(p):
        a,b,c=p[tri[:,0]],p[tri[:,1]],p[tri[:,2]]
        return (b[:,0]-a[:,0])*(c[:,1]-a[:,1])-(b[:,1]-a[:,1])*(c[:,0]-a[:,0])
    refs=areas(rest);lengths=np.sum((rest[edges[:,0]]-rest[edges[:,1]])**2,axis=1)
    if np.any(np.abs(refs)<1e-12) or np.any(lengths<=1e-20):raise ValueError('regional_geometry_degenerate_setup')
    indices={v:i for i,v in enumerate(moving)}
    def unpack(x):
        p=posed.copy();p[moving]+=budget*x.reshape(-1,2);return p
    def fun(x):
        p=unpack(x);ratio=areas(p)/refs;edge=np.sum((p[edges[:,0]]-p[edges[:,1]])**2,axis=1)/lengths
        return np.r_[ratio-.50001,1.99999-ratio,3.99999-edge]
    def jac(x):
        p=unpack(x);result=np.zeros((2*len(tri)+len(edges),2*len(moving)))
        for i,(a,b,c) in enumerate(tri):
            gradients=((p[b,1]-p[c,1],p[c,0]-p[b,0]),(p[c,1]-p[a,1],p[a,0]-p[c,0]),(p[a,1]-p[b,1],p[b,0]-p[a,0]))
            for v,g in zip((a,b,c),gradients):
                if v not in indices:continue
                j=2*indices[v];d=np.asarray(g)*budget/refs[i]
                result[i,j:j+2]=d;result[len(tri)+i,j:j+2]=-d
        for i,(a,b) in enumerate(edges):
            d=-2*(p[a]-p[b])*budget/lengths[i]
            for v,g in ((a,d),(b,-d)):
                if v in indices:result[2*len(tri)+i,2*indices[v]:2*indices[v]+2]=g
        return result
    return dict(type='ineq',fun=fun,jac=jac)
