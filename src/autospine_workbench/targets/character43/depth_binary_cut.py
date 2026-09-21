"""Deterministic bounded binary Potts solver with exact integer capacities."""
from collections import deque


def solve(unary,edges,fixed=None):
    n=len(unary);fixed=fixed or {}
    if not 1<=n<=4096 or len(edges)>16384:raise ValueError('depth_cut_resource_limit')
    if any(len(c)!=2 or any(type(v) is not int or not 0<=v<=10**9 for v in c) for c in unary):
        raise ValueError('depth_cut_unary')
    if any(type(i) is not int or not 0<=i<n or type(v) is not int or v not in (0,1) for i,v in fixed.items()):
        raise ValueError('depth_cut_fixed')
    for a,b,cost in edges:
        if type(a) is not int or type(b) is not int or not 0<=a<n or not 0<=b<n or a==b or type(cost) is not int or not 0<=cost<=10**9:
            raise ValueError('depth_cut_edge')
    hard=1+sum(sum(c) for c in unary)+sum(c for _,_,c in edges)
    graph=[[] for _ in range(n+2)];source=n;sink=n+1
    def add(a,b,c):
        graph[a].append([b,c,len(graph[b])]);graph[b].append([a,0,len(graph[a])-1])
    for i,(back,front) in enumerate(unary):
        add(source,i,back+(hard if fixed.get(i)==1 else 0))
        add(i,sink,front+(hard if fixed.get(i)==0 else 0))
    for a,b,cost in sorted(edges):add(a,b,cost);add(b,a,cost)
    augmentations=0
    while True:
        parent={source:None};queue=deque([source])
        while queue and sink not in parent:
            a=queue.popleft()
            for index,(b,capacity,_) in enumerate(graph[a]):
                if capacity>0 and b not in parent:parent[b]=(a,index);queue.append(b)
        if sink not in parent:break
        amount=hard;node=sink
        while node!=source:
            a,index=parent[node];amount=min(amount,graph[a][index][1]);node=a
        node=sink
        while node!=source:
            a,index=parent[node];edge=graph[a][index];edge[1]-=amount
            graph[node][edge[2]][1]+=amount;node=a
        augmentations+=1
        if augmentations>100000:raise ValueError('depth_cut_iteration_limit')
    labels=[int(i in parent) for i in range(n)]
    if any(labels[i]!=v for i,v in fixed.items()):raise ValueError('depth_cut_fixed_violated')
    energy=sum(c[labels[i]] for i,c in enumerate(unary))+sum(c for a,b,c in edges if labels[a]!=labels[b])
    return dict(labels=labels,energy=energy,augmentations=augmentations)
