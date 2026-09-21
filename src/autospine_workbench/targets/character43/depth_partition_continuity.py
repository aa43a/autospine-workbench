"""Locate new opaque visibility cuts between adjacent source triangles."""
from collections import defaultdict
import math
import numpy as np
from .affine_pose import sample
from ..spine43.seam_raster import texture
from ..spine43.seam_direct_alpha import sample as alpha_sample


def boundaries(source,partition):
    owners=defaultdict(dict)
    for row in partition['regions']:
        for index in row['triangles']:
            if index in owners[row['source_slot']]:raise ValueError('continuity_duplicate_triangle')
            owners[row['source_slot']][index]=row['slot']
    output=[]
    for name,mapping in owners.items():
        mesh=source['skins'][0]['attachments'][name][name];flat=mesh['triangles'];edges=defaultdict(list)
        if set(mapping)!=set(range(len(flat)//3)):raise ValueError('continuity_triangle_inventory')
        for index in mapping:
            tri=flat[3*index:3*index+3]
            for a,b in zip(tri,tri[1:]+tri[:1]):edges[tuple(sorted((a,b)))].append(index)
        for edge,triangles in edges.items():
            if len(triangles)>2:raise ValueError('continuity_nonmanifold_edge')
            if len(triangles)==2 and mapping[triangles[0]]!=mapping[triangles[1]]:
                output.append(dict(source_slot=name,edge=list(edge),triangles=triangles,
                    regions=[mapping[t] for t in triangles]))
    return output


def ranks(document,animation,time):
    names=[s['name'] for s in document['slots']];rank={n:i for i,n in enumerate(names)}
    frames=document['animations'][animation].get('drawOrder',[])
    keys=[r for r in frames if r.get('time',0)<=time]
    if keys:
        offsets=keys[-1].get('offsets',[])
        if {r['slot'] for r in offsets}!=set(names):raise ValueError('continuity_full_order_required')
        rank={r['slot']:rank[r['slot']]+r['offset'] for r in offsets}
        if sorted(rank.values())!=list(range(len(names))):raise ValueError('continuity_order_inventory')
    return rank


def analyze(source,candidate,partition,files,slot_bodies,times,*,work_limit=64_000_000):
    if not times or len(times)>1025 or any(not math.isfinite(t) or t<0 for t in times):
        raise ValueError('continuity_sample_times')
    edges=boundaries(source,partition);rows=[];used=0
    setup=ranks(dict(candidate,animations={'setup':{}}),'setup',0)
    meshes=source['skins'][0]['attachments'];textures={}
    def image(name):
        if name not in textures:
            mesh=meshes[name][name];textures[name]=texture(files['images/'+mesh.get('path',name)+'.png'])
        return textures[name]
    for time in times:
        order=ranks(candidate,'external-motion',time);pose=sample(source,'external-motion',time)[0]
        pending=defaultdict(list)
        for edge in edges:
            name=edge['source_slot'];a,b=edge['regions'];mesh=meshes[name][name]
            for body in slot_bodies[name]:
                # Ignore boundaries whose visibility side was already different.
                if (order[a]>order[body])==(order[b]>order[body]):continue
                if (setup[a]>setup[body])!=(setup[b]>setup[body]):continue
                points=np.asarray(pose[name]);ends=points[edge['edge']]
                count=min(33,max(3,math.ceil(math.dist(*ends))+1))
                cost=2*count*(len(meshes[body][body]['triangles'])//3+1)
                if used+cost>work_limit:
                    return dict(profile='adjacent-opaque-visibility-cut-v1',status='incomplete',records=rows,
                        reason_code='continuity_work_budget',work_used=used,authority='none',selected=False)
                used+=cost
                base=np.linspace(ends[0],ends[1],count)
                sides=[];opaque=[]
                for triangle in edge['triangles']:
                    indices=mesh['triangles'][3*triangle:3*triangle+3]
                    centre=points[indices].mean(axis=0);distance=np.linalg.norm(centre-base,axis=1)
                    blend=np.minimum(.25,.5/np.maximum(distance,1e-12))
                    probes=base+(centre-base)*blend[:,None]
                    values,_=alpha_sample(dict(mesh,triangles=indices),points,image(name),probes)
                    sides.append(probes);opaque.append(values>=8)
                pending[body].append((edge,sides,opaque))
        for body,items in pending.items():
            all_points=np.concatenate([side for _,sides,_ in items for side in sides])
            mesh=meshes[body][body]
            values,_=alpha_sample(mesh,pose[body],image(body),all_points);offset=0
            for edge,sides,opaque in items:
                count=len(sides[0]);va=values[offset:offset+count];vb=values[offset+count:offset+2*count];offset+=2*count
                hit=opaque[0]&opaque[1]&(va>=8)&(vb>=8)
                if hit.any():
                    index=int(np.flatnonzero(hit)[len(np.flatnonzero(hit))//2])
                    rows.append(dict(edge,time=time,body=body,sampled_points=count,opaque_cut_points=int(hit.sum()),
                        point=((sides[0][index]+sides[1][index])/2).tolist(),
                        front_region=next(r for r in edge['regions'] if order[r]>order[body]),
                        changed_region=next(r for r in edge['regions'] if (order[r]>order[body])!=(setup[r]>setup[body])),
                        reason_code='new_opaque_partition_boundary_requires_review'))
    return dict(profile='adjacent-opaque-visibility-cut-v1',status='needs_review' if rows else 'no_sampled_cut',
        records=rows,work_used=used,edge_count=len(edges),sampled_frames=len(times),authority='none',selected=False,
        scope='sampled_local_visibility_boundary_not_proof_of_crack_or_visual_acceptance')
