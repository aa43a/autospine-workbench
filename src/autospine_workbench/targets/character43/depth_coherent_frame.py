"""Experimental adjacency/temporal inference; observed depth is never overwritten."""
from collections import Counter,defaultdict
from .depth_partition_trace import classify
from .depth_binary_cut import solve

PROFILE='opaque-triangle-adjacency-potts8-temporal1-v1-experiment'


def adjacency(mesh):
    flat=mesh['triangles'];edges=defaultdict(list)
    if len(flat)%3:raise ValueError('coherent_triangle_inventory')
    for i in range(len(flat)//3):
        tri=flat[3*i:3*i+3]
        for a,b in zip(tri,tri[1:]+tri[:1]):edges[tuple(sorted((a,b)))].append(i)
    if any(len(v)>2 for v in edges.values()):raise ValueError('coherent_nonmanifold')
    return sorted({tuple(sorted(v)) for v in edges.values() if len(v)==2})


def infer(mesh,row,previous,setup_front):
    n=len(mesh['triangles'])//3
    if len(previous)!=n or any(v not in (0,1) for v in previous):raise ValueError('coherent_previous_inventory')
    counts={int(i):c for i,c in row['triangles'].items()}
    if len(counts)!=len(row['triangles']) or any(not 0<=i<n for i in counts):raise ValueError('coherent_triangle_inventory')
    if row['status'] not in ('unmeasured','no_overlap','uniform_front_proxy','uniform_back_proxy','requires_partition_or_more_depth'):
        raise ValueError('coherent_sample_status')
    if row['status']=='no_overlap' and any(sum(c.values()) for c in counts.values()):raise ValueError('coherent_overlap_inventory')
    states=['U']*n if row['status']=='unmeasured' else [classify(counts.get(i,{})) for i in range(n)]
    fixed={};unary=[]
    for i,state in enumerate(states):
        if state in ('F','B'):fixed[i]=int(state=='F')
        elif state in ('U','M'):fixed[i]=int(setup_front)
        unary.append((int(previous[i]!=0),int(previous[i]!=1)))
    edges=[(a,b,8) for a,b in adjacency(mesh) if states[a]!='N' and states[b]!='N']
    result=solve(unary,edges,fixed)
    result.update(profile=PROFILE,observed_states=''.join(states),state_counts=dict(Counter(states)),
        inferred_triangles=[i for i,s in enumerate(states) if s=='A'],
        unresolved_triangles=[i for i,s in enumerate(states) if s in ('U','M')],
        transition_count=sum(a!=b for a,b in zip(previous,result['labels'])),
        spatial_cuts=sum(result['labels'][a]!=result['labels'][b] for a,b,_ in edges),
        authority='none',selected=False,scope='regularized_proxy_inference_not_observed_depth_or_visual_acceptance')
    return result
