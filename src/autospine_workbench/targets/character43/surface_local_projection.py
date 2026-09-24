"""Bounded diagnostic 3D area/edge projection; failure never authorizes adoption."""
import numpy as np


def solve(rest,posed,triangles,free,budget=22.,iterations=300):
    rest,source=np.asarray(rest,float),np.asarray(posed,float);tri=np.asarray(triangles)
    if (rest.ndim!=2 or rest.shape[1]!=3 or source.shape!=rest.shape or
            not np.isfinite(rest).all() or not np.isfinite(source).all() or
            tri.ndim!=2 or tri.shape[1]!=3 or not tri.size or
            not np.issubdtype(tri.dtype,np.integer) or tri.min()<0 or tri.max()>=len(rest) or
            not np.isfinite(budget) or budget<=0 or type(iterations) is not int or not 1<=iterations<=1000 or
            len(set(free))!=len(free) or any(type(i) is not int or not 0<=i<len(rest) for i in free)):
        raise ValueError('surface_local_input')
    edges=np.unique(np.sort(np.concatenate((tri[:,[0,1]],tri[:,[1,2]],tri[:,[2,0]])),axis=1),axis=0)
    def areas(p):return np.linalg.norm(np.cross(p[tri[:,1]]-p[tri[:,0]],p[tri[:,2]]-p[tri[:,0]]),axis=1)/2
    refs=areas(rest);lengths=np.linalg.norm(rest[edges[:,1]]-rest[edges[:,0]],axis=1)
    if (refs<=1e-12).any() or (lengths<=1e-12).any():raise ValueError('surface_local_degenerate_rest')
    movable=np.zeros(len(rest));movable[free]=1;p=source.copy()
    for iteration in range(iterations):
        q=p[tri];cross=np.cross(q[:,1]-q[:,0],q[:,2]-q[:,0]);norm=np.linalg.norm(cross,axis=1)
        area=norm/2;target=np.clip(area,.505*refs,1.995*refs);active=np.where(abs(target-area)>1e-10)[0]
        delta=np.zeros_like(p);counts=np.zeros(len(p))
        if len(active):
            ids=tri[active];q=q[active];normal=cross[active]/np.maximum(norm[active,None],1e-20)
            gradient=np.stack((np.cross(q[:,1]-q[:,2],normal),np.cross(q[:,2]-q[:,0],normal),
                               np.cross(q[:,0]-q[:,1],normal)),axis=1)/2
            gradient*=movable[ids,None];den=(gradient*gradient).sum(axis=(1,2))
            step=(target[active]-area[active])/np.maximum(den,1e-20)
            updates=gradient*step[:,None,None]
            np.add.at(delta,ids.ravel(),updates.reshape(-1,3));np.add.at(counts,ids.ravel(),movable[ids].ravel())
        vectors=p[edges[:,1]]-p[edges[:,0]];size=np.linalg.norm(vectors,axis=1)
        active=np.where(size>1.995*lengths)[0]
        for k in active:
            a,b=edges[k];den=movable[a]+movable[b]
            if not den:continue
            correction=vectors[k]/size[k]*(size[k]-1.995*lengths[k])/den
            delta[a]+=movable[a]*correction;delta[b]-=movable[b]*correction
            counts[a]+=movable[a];counts[b]+=movable[b]
        p+=.5*delta/np.maximum(counts[:,None],1)
        displacement=p-source;norm=np.linalg.norm(displacement,axis=1)
        p=source+displacement*np.minimum(1,budget/np.maximum(norm,1e-20))[:,None]
        p[movable==0]=source[movable==0]
        ratios=areas(p)/refs;stretch=np.linalg.norm(p[edges[:,1]]-p[edges[:,0]],axis=1)/lengths
        if (ratios>=.5).all() and (ratios<=2).all() and (stretch<=2).all():break
    return p,dict(iterations=iteration+1,free_vertices=len(free),budget=budget,
        maximum_displacement=float(np.max(np.linalg.norm(p-source,axis=1))),
        failed_area_triangles=int(((ratios<.5)|(ratios>2)).sum()),
        overstretched_edges=int((stretch>2).sum()),
        geometry_passed=bool((ratios>=.5).all() and (ratios<=2).all() and (stretch<=2).all()),
        accepted=False,limitations=['no_self_intersection_or_volume_gate','no_material_or_contact_acceptance'])
