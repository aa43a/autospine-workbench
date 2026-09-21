"""Propose a narrow proximal deform collar next to a terminal joint blend."""
import math
from statistics import median


def extend_proximal_ring(collar,triangles,influences,bones):
    seeds=set(collar['vertices'])
    if not seeds:return dict(collar)
    neighbors={v for tri in triangles if seeds.intersection(tri) for v in tri}
    added=sorted(v for v in neighbors-seeds if {bones[i]['name'] for i,w in influences[v] if w>0}=={collar['parent']})
    result=dict(collar,profile='terminal-proximal-extra-ring-v1-experiment',
                vertices=sorted(seeds|set(added)),additional_ring_vertices=added)
    if 'radius_px' in result:result['seed_radius_px']=result.pop('radius_px')
    return result


def propose(points,triangles,influences,bones,pose,parent,child):
    lookup={b['name']:b for b in bones}
    if lookup[child].get('parent')!=parent:raise ValueError('joint_collar_direct_chain_required')
    owners=[{bones[i]['name'] for i,w in entries if w>0} for entries in influences]
    mixed={i for i,s in enumerate(owners) if s=={parent,child}}
    edges={tuple(sorted((t[i],t[(i+1)%3]))) for t in triangles for i in range(3)}
    adjacent={v for a,b in edges if a in mixed or b in mixed for v in (a,b)}
    lengths=[math.dist(points[a],points[b]) for a,b in edges if a in mixed or b in mixed]
    if not lengths:return dict(profile='terminal-proximal-collar-v1',vertices=[],radius_px=0,authority='none',selected=False)
    anchor=pose[child][4:6];parent_origin=pose[parent][4:6]
    radius=min(2*median(lengths),.15*math.dist(anchor,parent_origin))
    added=sorted(v for v in adjacent if owners[v]=={parent} and math.dist(points[v],anchor)<=radius)
    return dict(profile='terminal-proximal-collar-v1',vertices=added,radius_px=radius,parent=parent,child=child,
                authority='none',selected=False,scope='proximal_deform_candidates_distal_fixed_vertices_preserved')
