"""Attachment-interface roots measured from exact triangle ownership."""
from collections import defaultdict
from copy import deepcopy
import math
from .sleeve_helpers import frames
from .sleeve_regions import validate
from .component_distal_guard import inventory,gate
from .component_local_solver import metrics
from .component_temporal_qa import passed
from ..joints.mesh_weights import _rotate,_deform
from ...resolved_project import canonical_sha256


def interface(vertices,triangles,assignments):
    if len(triangles)!=len(assignments):raise ValueError('cloth_interface_inventory')
    labels=defaultdict(set)
    for tri,item in zip(triangles,assignments):
        for a,b in zip(tri,tri[1:]+tri[:1]):labels[tuple(sorted((a,b)))].add(item['role'])
    edges=sorted(e for e,r in labels.items() if 'hanging_cloth' in r and r & {'sleeve','cuff'} and not r & {'hand','unknown'})
    adjacency=defaultdict(set)
    for a,b in edges:adjacency[a].add(b);adjacency[b].add(a)
    unseen=set(adjacency);components=0
    while unseen:
        components+=1;stack=[min(unseen)]
        while stack:
            i=stack.pop()
            if i not in unseen:continue
            unseen.remove(i);stack.extend(sorted(adjacency[i]&unseen))
    lengths=[math.dist(vertices[a],vertices[b]) for a,b in edges];total=sum(lengths)
    root=None
    if total>1e-9:root=[sum((vertices[a][k]+vertices[b][k])*.5*l for (a,b),l in zip(edges,lengths))/total for k in (0,1)]
    return dict(edges=[list(e) for e in edges],connected_components=components,total_length=total,root_xy=root,
                reason_code='candidate_interface_root' if components==1 and root else 'ambiguous_or_missing_interface')


def build(source,garment,candidate,draft,skeleton):
    if (source['schema']!='autospine.sleeve-helper/v1' or source['source_sha256']!=canonical_sha256(garment)
            or source['skeleton_sha256']!=canonical_sha256(skeleton) or source.get('authority')!='none'
            or source.get('production_authorized') is not False or garment['draft_sha256']!=canonical_sha256(draft)
            or garment['candidate_sha256']!=canonical_sha256(candidate)):
        raise ValueError('cloth_interface_source_mismatch')
    draft=validate(draft,candidate);labels=inventory(draft['records']);meshes=inventory(garment['records'])
    bones={b['id']:b for b in skeleton['bones']};rows=deepcopy(source['records'])
    for row in rows:
        if 'helper' not in row:continue
        key=row['layer_id'],row['component_id'];mesh=meshes[key]['mesh'];measure=interface(mesh['vertices_xy'],mesh['triangles'],labels[key]['assignments'])
        row['interface_root']=dict(measure,selected=False)
        if measure['reason_code']!='candidate_interface_root':continue
        helper=deepcopy(row['helper']);root=measure['root_xy'];tip=helper['tail_xy'];length=math.dist(root,tip)
        if length<=1e-6:row['interface_root']['reason_code']='degenerate_interface_direction';continue
        rotation=math.degrees(math.atan2(tip[1]-root[1],tip[0]-root[0]));parent=bones[helper['parent_id']]
        helper.update(head_xy=root,length=length,world_rotation_degrees=rotation,
            setup_local=dict(rotation_degrees=rotation-parent['world_rotation_degrees'],translation_xy=_rotate([root[k]-parent['head_xy'][k] for k in (0,1)],-parent['world_rotation_degrees'])),
            provenance=dict(kind='candidate',reason='length_weighted_semantic_interface',reviewed=False))
        weights=deepcopy(row['weights'])
        for p,entries in zip(mesh['vertices_xy'],weights):
            for entry in entries:
                if entry['bone_id']==helper['id']:entry['local_xy']=_rotate([p[k]-root[k] for k in (0,1)],-rotation)
        chain=[bones[b] for b in mesh['bone_ids']]+[helper];newtracks=[];reasons=[];gain=False
        for old in row['tracks']:
            qa=[];samples=[];low,high=old['angle_range']
            for tick in range(129):
                angle=low+(high-low)*tick/128;transform=frames(chain,{old['bone_id']:angle});points=_deform(weights,transform)
                qa.append(metrics(mesh['vertices_xy'],points,mesh['triangles']))
                if tick%4==0:
                    display=[]
                    for b in chain:
                        head,rot=transform[b['id']];delta=_rotate([math.dist(b['head_xy'],b['tail_xy']),0],rot)
                        display.append(dict(id=b['id'],head_xy=head,tail_xy=[head[k]+delta[k] for k in (0,1)]))
                    samples.append(dict(angle=angle,points=points,bones=display))
            rejected,improved=gate(old['qa'],qa);reasons.extend(rejected);gain |= improved
            newtracks.append(dict(bone_id=old['bone_id'],angle_range=old['angle_range'],qa=qa,samples=samples,failed_ticks=sum(not passed(q) for q in qa)))
        rest=_deform(weights,frames(chain,{}));error=max(math.dist(a,b) for a,b in zip(rest,mesh['vertices_xy']))
        selected=not reasons and gain and error<=1e-7
        row['interface_root'].update(selected=selected,reason_codes=sorted(set(reasons)) or (['sampled_improvement'] if selected else ['no_sampled_gain']),
            baseline_failed_ticks=[t['failed_ticks'] for t in row['tracks']],trial_failed_ticks=[t['failed_ticks'] for t in newtracks],
            trial_qa=[dict(bone_id=t['bone_id'],qa=t['qa']) for t in newtracks],trial_setup_error=error)
        if selected:row.update(helper=helper,weights=weights,tracks=newtracks,setup_error=error)
    return dict(schema='autospine.sleeve-interface-root/v1',profile='semantic-interface-length-root-guard129-v1',
                project_id=source['project_id'],source_sha256=canonical_sha256(source),skeleton_sha256=canonical_sha256(skeleton),records=rows,
                authority='none',production_authorized=False,runtime_status='not_evaluated')
