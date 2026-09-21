"""Bounded conditional block cuts; convergence is local, not global optimality."""
from .depth_binary_cut import solve


def energy(unary,edges,labels):
    return sum(c[labels[i]] for i,c in enumerate(unary))+sum(w for a,b,w in edges if labels[a]!=labels[b])


def solve_blocks(unary,edges,initial,*,block_size=1024,sweeps=8):
    if not 1<=block_size<=1024 or not 1<=sweeps<=8:raise ValueError('depth_block_limits')
    if not 1<=len(unary)<=32768 or len(edges)>131072:raise ValueError('depth_block_resource_limit')
    if len(initial)!=len(unary) or any(type(v) is not int or v not in (0,1) for v in initial):
        raise ValueError('depth_block_initial')
    labels=list(initial);before=energy(unary,edges,labels)
    blocks=[list(range(i,min(i+block_size,len(labels)))) for i in range(0,len(labels),block_size)]
    for sweep in range(sweeps):
        start=list(labels)
        for block in blocks+list(reversed(blocks)):
            indices={v:i for i,v in enumerate(block)};costs=[list(unary[i]) for i in block];local=[]
            for a,b,w in edges:
                x,y=indices.get(a),indices.get(b)
                if x is not None and y is not None:local.append((x,y,w))
                elif (x is None)!=(y is None):
                    free,fixed=(x,b) if x is not None else (y,a)
                    costs[free][1-labels[fixed]]+=w
            result=solve(costs,local)
            for i,v in zip(block,result['labels']):labels[i]=v
        after=energy(unary,edges,labels)
        if after>energy(unary,edges,start):raise ValueError('depth_block_energy_increased')
        if labels==start:
            return dict(labels=labels,status='locally_stable',sweeps=sweep+1,energy=after,initial_energy=before)
    return dict(labels=list(initial),status='held_iteration_limit',sweeps=sweeps,energy=before,initial_energy=before)
