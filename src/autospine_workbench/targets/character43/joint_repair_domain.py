"""Topology-local correction freedom; terminal single-bone vertices stay pinned."""


def expand(influences, bones, triangles, rings=0):
    if type(rings) is not int or not 0<=rings<=2:
        raise ValueError('joint_domain_rings_invalid')
    owners=[{bones[b]['name'] for b,w in row if w>0} for row in influences]
    allowed={p+'_'+s for p in ('thigh','calf','upperarm','forearm') for s in ('l','r')}
    original=[sum(w>0 for _,w in row)>1 for row in influences]
    active={i for i,v in enumerate(original) if v}
    adjacency=[set() for _ in owners]
    for tri in triangles:
        if len(tri)!=3 or any(type(v) is not int or not 0<=v<len(owners) for v in tri):
            raise ValueError('joint_domain_topology_invalid')
        for v in tri:adjacency[v].update(set(tri)-{v})
    frontier=set(active)
    for _ in range(rings):
        extra={n for v in frontier for n in adjacency[v]
               if n not in active and owners[n] and owners[n]<=allowed}
        active|=extra;frontier=extra
    free=[i in active for i in range(len(owners))]
    return free,dict(profile='joint-topology-boundary-domain-v1-experiment',rings=rings,
        released_vertices=[i for i,(a,b) in enumerate(zip(original,free)) if b and not a],
        original_movable_vertices=[i for i,v in enumerate(original) if v],
        fixed_vertices=[i for i,v in enumerate(free) if not v],
        scope='local_corrective_freedom_not_binding_change_or_contact_acceptance')
