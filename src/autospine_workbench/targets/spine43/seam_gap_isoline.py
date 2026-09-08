"""Subpixel chord approximation to the bilinear interpolant of CPU alpha samples.

This is not direct GPU alpha evaluation. Saddle and exact-threshold cells remain
unresolved; nearest normals are gradient estimates at chord midpoints.
"""
import math
import numpy as np
from .seam_gap_boundary import probe as edge_probe


def contours(alpha, rect, subdivisions=4):
    if subdivisions not in (4, 8): raise ValueError('isoline_subdivision_profile')
    alpha=np.asarray(alpha,dtype=float)
    if alpha.ndim!=2 or not np.isfinite(alpha).all(): raise ValueError('isoline_nonfinite_field')
    height,width=alpha.shape; segments=[]; unresolved=[]
    for y in range(height-1):
        for x in range(width-1):
            corners=[alpha[y,x],alpha[y,x+1],alpha[y+1,x+1],alpha[y+1,x]]
            if min(corners)>8 or max(corners)<8: continue
            a=corners[0];b=corners[1]-a;c=corners[3]-a;d=corners[2]-a-b-c
            value=lambda u,v:a+b*u+c*v+d*u*v
            for iy in range(subdivisions):
                for ix in range(subdivisions):
                    points=[(ix/subdivisions,iy/subdivisions),((ix+1)/subdivisions,iy/subdivisions),
                            ((ix+1)/subdivisions,(iy+1)/subdivisions),(ix/subdivisions,(iy+1)/subdivisions)]
                    values=[value(*p) for p in points]
                    if min(values)>8 or max(values)<8: continue
                    box=[rect[0]+x+.5+points[0][0],-(rect[1]+y+.5+points[2][1]),
                         rect[0]+x+.5+points[2][0],-(rect[1]+y+.5+points[0][1])]
                    hits=[]
                    for i in range(4):
                        j=(i+1)%4
                        if (values[i]<8)!=(values[j]<8):
                            t=(8-values[i])/(values[j]-values[i])
                            hits.append([points[i][k]+t*(points[j][k]-points[i][k]) for k in (0,1)])
                    if any(abs(v-8)<1e-10 for v in values) or len(hits)!=2:
                        unresolved.append(box);continue
                    u,v=[sum(p[k] for p in hits)/2 for k in (0,1)]
                    gx,gy=b+d*v,c+d*u;length=math.hypot(gx,gy)
                    if length<1e-10:
                        unresolved.append(box);continue
                    world=lambda p:[rect[0]+x+.5+p[0],-(rect[1]+y+.5+p[1])]
                    segments.append(dict(a=world(hits[0]),b=world(hits[1]),normal=[-gx/length,gy/length]))
    return dict(segments=segments,unresolved_boxes=unresolved)


def probe(point, boundaries):
    result=edge_probe(point,[b['segments'] for b in boundaries])
    nearby=[]
    for boundary in boundaries:
        nearby.append(sum(math.hypot(max(box[0]-point[0],0,point[0]-box[2]),
                                     max(box[1]-point[1],0,point[1]-box[3]))<=4
                          for box in boundary['unresolved_boxes']))
    result['unresolved_cells_within4']=nearby
    if any(nearby): result['evidence']='unresolved_isoline_neighborhood'
    return result
