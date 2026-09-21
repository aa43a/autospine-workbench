"""Exact derivatives of area, edge and displacement inequalities."""
import numpy as np


def jacobian(points,triangles,refs,edges,lengths,indices,budget,variables):
    size=len(indices);columns={int(v):2*i for i,v in enumerate(indices)}
    area=np.zeros((len(triangles),2*size));edge=np.zeros((len(edges),2*size))
    for row,(a,b,c) in enumerate(triangles):
        pa,pb,pc=points[a],points[b],points[c]
        gradients=((pb[1]-pc[1],pc[0]-pb[0]),(pc[1]-pa[1],pa[0]-pc[0]),(pa[1]-pb[1],pb[0]-pa[0]))
        for vertex,g in zip((a,b,c),gradients):
            if int(vertex) in columns:
                col=columns[int(vertex)];area[row,col:col+2]=np.asarray(g)*budget/(2*refs[row])
    for row,(a,b) in enumerate(edges):
        g=-2*(points[a]-points[b])*budget/max(lengths[row]**2,1e-20)
        for vertex,sign in ((a,1),(b,-1)):
            if int(vertex) in columns:
                col=columns[int(vertex)];edge[row,col:col+2]=g*sign
    disk=np.zeros((size,2*size))
    for i in range(size):disk[i,2*i:2*i+2]=-2*variables[2*i:2*i+2]
    return np.concatenate((area,-area,edge,disk))
