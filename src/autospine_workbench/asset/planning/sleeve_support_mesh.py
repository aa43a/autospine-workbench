"""Conforming garment interface supports with exact affine LBS prolongation."""
from collections import defaultdict
from copy import deepcopy
from .sleeve_connection_domain import prepare,domain
from .cloth_interface_root import interface
from ...resolved_project import canonical_sha256


def blend(weights,indices):
    totals=defaultdict(lambda:[0.,0.,0.])
    for i in indices:
        for e in weights[i]:
            w=e['weight']/len(indices);v=totals[e['bone_id']]
            v[0]+=w;v[1]+=w*e['local_xy'][0];v[2]+=w*e['local_xy'][1]
    return [dict(bone_id=b,weight=v[0],local_xy=[v[1]/v[0],v[2]/v[0]]) for b,v in sorted(totals.items()) if v[0]>0]


def refine(row,uvs,assignments):
    triangles=row['triangles'];points=row['setup_vertices'];weights=row['weights']
    if len(assignments)!=len(triangles) or len(uvs)!=len(points) or len(weights)!=len(points):
        raise ValueError('sleeve_support_inventory')
    vertex_roles=defaultdict(set);edges=defaultdict(list)
    garment={'cuff','sleeve','hanging_cloth'}
    for i,(t,a) in enumerate(zip(triangles,assignments)):
        for v in t:vertex_roles[v].add(a['role'])
        for a,b in zip(t,t[1:]+t[:1]):edges[tuple(sorted((a,b)))].append(i)
    # Refine garment triangles incident to a body/uncertain boundary or cuff structure.
    targets={i for i,(t,a) in enumerate(zip(triangles,assignments)) if a['role'] in garment
             and (a['role']=='cuff' or any(not vertex_roles[v]<=garment for v in t))}
    marked=sorted(e for e,owners in edges.items() if any(i in targets for i in owners))
    newpoints=deepcopy(points);newuvs=deepcopy(uvs);newweights=deepcopy(weights);parents=[[i] for i in range(len(points))]
    def append(indices):
        index=len(newpoints);newpoints.append([sum(points[i][k] for i in indices)/len(indices) for k in (0,1)])
        newuvs.append([sum(uvs[i][k] for i in indices)/len(indices) for k in (0,1)])
        newweights.append(blend(weights,indices));parents.append(list(indices));return index
    midpoints={e:append(e) for e in marked};newtri=[];newlabels=[];origins=[]
    for i,(tri,label) in enumerate(zip(triangles,assignments)):
        boundary=[]
        for a,b in zip(tri,tri[1:]+tri[:1]):
            boundary.append(a);edge=tuple(sorted((a,b)))
            if edge in midpoints:boundary.append(midpoints[edge])
        if len(boundary)==3:parts=[tri[:]]
        else:
            center=append(tri);parts=[[center,a,b] for a,b in zip(boundary,boundary[1:]+boundary[:1])]
        for t in parts:newtri.append(t);newlabels.append(deepcopy(label));origins.append(i)
    return dict(vertices_xy=newpoints,uvs=newuvs,weights=newweights,triangles=newtri,assignments=newlabels,
        source_triangle_indices=origins,vertex_source_indices=parents,profile='garment-interface-affine-support-v1')


def prepare_support(source,garment,draft):
    coarse_domains=prepare(source,garment,draft)
    labels={(r['layer_id'],r['component_id']):r['assignments'] for r in draft['records']}
    meshes={(r['layer_id'],r['component_id']):r['mesh'] for r in garment['records']}
    amended=deepcopy(source);domains={}
    for row in amended['records']:
        if 'helper' not in row:continue
        key=row['layer_id'],row['component_id'];mesh=meshes[key]
        support=refine(row,mesh['uvs'],labels[key]);support['source_mesh_sha256']=canonical_sha256(mesh)
        support['coarse_constraints']=dict(vertices_xy=deepcopy(row['setup_vertices']),triangles=deepcopy(row['triangles']),
            free_vertices=coarse_domains[key]['free_vertices'])
        row.update(setup_vertices=support['vertices_xy'],triangles=support['triangles'],weights=support['weights'],support_mesh=support)
        row['interface_root']=dict(interface(support['vertices_xy'],support['triangles'],support['assignments']),selected=False)
        d=domain(support['triangles'],support['assignments']);d['budget_policy']='one-free-area-bound-cap50-v1';domains[key]=d
        row['cloth_vertices']=[int(i) for i,r in d['vertex_roles'].items() if r==['hanging_cloth']]
    return amended,domains
