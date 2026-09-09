"""Fixed-iteration graph transition; hand/unknown pinned, garment interior isolated."""
from copy import deepcopy


def reweight(mesh, assignments):
    if len(assignments)!=len(mesh['triangles']):raise ValueError('sleeve_boundary_inventory')
    count=len(mesh['vertices_xy']);roles=[set() for _ in range(count)];neighbors=[set() for _ in range(count)]
    for tri,item in zip(mesh['triangles'],assignments):
        for i in tri:roles[i].add(item['role']);neighbors[i].update(j for j in tri if j!=i)
    values=[1.]*count;free=[];pinned=[]
    for i,r in enumerate(roles):
        if not r or r & {'hand','unknown'}:pinned.append(i)
        elif r <= {'sleeve','hanging_cloth'}:values[i]=0.;pinned.append(i)
        else:free.append(i)
    # Deterministic Jacobi sweeps; no character name, mesh scale or tuned per-character width.
    for _ in range(64):
        trial=values[:]
        for i in free:
            adjacent=sorted(neighbors[i])
            if adjacent:trial[i]=sum(values[j] for j in adjacent)/len(adjacent)
        values=trial
    result=deepcopy(mesh)
    for row,ratio in zip(result['weights'],values):
        if [w['bone_id'] for w in row]!=mesh['bone_ids']:raise ValueError('sleeve_boundary_bone_order')
        transfer=row[2]['weight']*(1-ratio)
        row[2]['weight']-=transfer;row[1]['weight']+=transfer
    return result,dict(iterations=64,free_vertices=free,pinned_vertices=pinned,hand_retention=values)
