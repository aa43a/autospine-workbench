"""Semantic cuff probes and conservative software coverage; not framebuffer evidence."""
from collections import defaultdict
import math


def probes(attachment,assignments,alpha,*,profile='three-point-v1'):
    import numpy as np
    if profile not in ('three-point-v1','source-length-v2'):raise ValueError('sleeve_contact_probe_profile')
    flat=attachment['triangles'];triangles=[flat[i:i+3] for i in range(0,len(flat),3)]
    if len(triangles)!=len(assignments):raise ValueError('sleeve_contact_assignment_inventory')
    uvs=np.asarray(attachment['uvs'],dtype=float).reshape(-1,2);height,width=alpha.shape
    edges=defaultdict(list)
    for i,t in enumerate(triangles):
        for a,b in zip(t,t[1:]+t[:1]):edges[tuple(sorted((a,b)))].append(i)
    result=[]
    for edge,incident in sorted(edges.items()):
        roles={assignments[i]['role'] for i in incident}
        if 'cuff' not in roles or not roles&{'hand','sleeve','hanging_cloth'}:continue
        if len(incident)!=2:raise ValueError('sleeve_contact_nonmanifold')
        samples=[]
        parameters=(.25,.5,.75)
        if profile=='source-length-v2':
            length=float(np.linalg.norm((uvs[edge[1]]-uvs[edge[0]])*[width,height]))
            if not math.isfinite(length) or length>100000:raise ValueError('sleeve_contact_edge_length')
            count=max(1,math.ceil(length))
            parameters=tuple((i+.5)/count for i in range(count))
        for u in parameters:
            uv=uvs[edge[0]]*(1-u)+uvs[edge[1]]*u;x,y=math.floor(uv[0]*width),math.floor(uv[1]*height)
            # Require a fully opaque source margin; transparent exterior is not a seam crack.
            visible=1<=x<width-1 and 1<=y<height-1 and float(np.min(alpha[y-1:y+2,x-1:x+2]))>=224
            if visible:samples.append(dict(u=u,source_uv=uv.tolist(),source_min_alpha=float(np.min(alpha[y-1:y+2,x-1:x+2]))))
        result.append(dict(edge=list(edge),triangles=incident,roles=sorted(roles),samples=samples,
            observability='opaque_margin' if samples else 'source_alpha_unobservable'))
    return result


def coverage(attachment,vertices,alpha,locations):
    """Sample native pixel centers with bilinear texture alpha and triangle coverage."""
    import numpy as np
    if not locations:return []
    points=np.array(vertices,dtype=float,copy=True);points[:,1]*=-1
    pixels=np.floor(np.asarray(locations,dtype=float))+.5;uvs=np.asarray(attachment['uvs']).reshape(-1,2)
    out=np.zeros(len(pixels));height,width=alpha.shape;flat=attachment['triangles']
    for offset in range(0,len(flat),3):
        idx=flat[offset:offset+3];a,b,c=points[idx]
        det=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
        if abs(det)<1e-12:continue
        u=((b[1]-c[1])*(pixels[:,0]-c[0])+(c[0]-b[0])*(pixels[:,1]-c[1]))/det
        v=((c[1]-a[1])*(pixels[:,0]-c[0])+(a[0]-c[0])*(pixels[:,1]-c[1]))/det;t=1-u-v
        indices=np.flatnonzero((u>=-1e-9)&(v>=-1e-9)&(t>=-1e-9))
        if not len(indices):continue
        uv=u[indices,None]*uvs[idx[0]]+v[indices,None]*uvs[idx[1]]+t[indices,None]*uvs[idx[2]]
        tex=uv*[width,height]-.5;ij=np.floor(tex).astype(int);f=tex-ij;sample=np.zeros(len(indices))
        for dx,dy in ((0,0),(1,0),(0,1),(1,1)):
            x,y=ij[:,0]+dx,ij[:,1]+dy;valid=(x>=0)&(x<width)&(y>=0)&(y<height)
            weights=(f[:,0] if dx else 1-f[:,0])*(f[:,1] if dy else 1-f[:,1])
            sample+=np.where(valid,alpha[np.clip(y,0,height-1),np.clip(x,0,width-1)]*weights,0)
        out[indices]=np.maximum(out[indices],sample)
    return out.tolist()


def analyze(attachment,alpha,interfaces,animations):
    selected=[(i,s) for i,r in enumerate(interfaces) for s in r['samples']]
    minimum=255.;failures=[];count=0;failed=0;tracks=[]
    for name,frames in sorted(animations.items()):
        track_failed=0
        for frame in frames:
            vertices=frame['points'];locations=[]
            for i,s in selected:
                a,b=(vertices[j] for j in interfaces[i]['edge']);u=s['u']
                locations.append([a[0]*(1-u)+b[0]*u,-a[1]*(1-u)-b[1]*u])
            values=coverage(attachment,vertices,alpha,locations);count+=len(values)
            for (i,s),p,value in zip(selected,locations,values):
                minimum=min(minimum,value)
                if value<8:
                    failed+=1;track_failed+=1
                    if len(failures)<100:failures.append(dict(animation=name,time=frame['time'],interface=i,u=s['u'],world_xy=p,alpha=value))
        tracks.append(dict(animation=name,frames=len(frames),failed_samples=track_failed))
    missing=sum(not r['samples'] for r in interfaces)
    return dict(profile='cuff-native-pixel-bilinear-alpha8-v1',status='cpu_coverage_passed' if count and not failed and not missing else 'needs_review',
        tested_samples=count,failed_samples=failed,min_alpha=minimum if count else None,unobservable_interfaces=missing,
        interfaces=interfaces,tracks=tracks,failures=failures,failures_truncated=failed>len(failures),
        framebuffer_status='not_evaluated',authority='none',production_authorized=False)
