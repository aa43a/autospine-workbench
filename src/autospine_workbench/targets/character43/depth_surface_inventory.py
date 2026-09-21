"""Model routing from rendered influences, never from character/layer names."""
import math
import re

MODEL_ROLES={'torso','garment_plane_candidate','arm.l','arm.r','leg.l','leg.r'}


def route(traces,inventory):
    roles={r['slot']:r['role'] for r in inventory['surfaces']};selected={};held={}
    for arm,rows in traces.items():
        for row in rows:
            body=row['body'];role=roles[body]
            if role in MODEL_ROLES:selected.setdefault(arm,[]).append(row)
            else:held[arm,body]=dict(arm=arm,body=body,role=role,policy='preserve_setup_without_depth_claim')
    return selected,list(held.values())


def influences(document,slot,mesh):
    if mesh.get('type')!='mesh':return None
    used=set(mesh['triangles']);data=mesh['vertices'];count=len(mesh['uvs'])//2
    if len(mesh['uvs'])%2 or len(mesh['triangles'])%3 or any(type(i) is not int or not 0<=i<count for i in used):
        raise ValueError('surface_inventory_mesh_indices')
    if not used:return set()
    if len(data)==len(mesh['uvs']):return {slot['bone']}
    cursor=0;vertex=0;names=set()
    while cursor<len(data):
        n=data[cursor];cursor+=1
        if type(n) is not int or n<1 or cursor+4*n>len(data):raise ValueError('surface_inventory_weights')
        total=0.;local=set()
        for _ in range(n):
            index,x,y,weight=data[cursor:cursor+4];cursor+=4
            if (type(index) is not int or not 0<=index<len(document['bones']) or
                    not all(math.isfinite(v) for v in (x,y,weight)) or weight<0):raise ValueError('surface_inventory_weights')
            total+=weight
            if weight>0:local.add(document['bones'][index]['name'])
        if vertex in used:
            if abs(total-1)>1e-6:raise ValueError('surface_inventory_weight_sum')
            names.update(local)
        vertex+=1
    if vertex!=count:raise ValueError('surface_inventory_vertex_count')
    return names


def classify(names,bones):
    if names is None:return 'unsupported_attachment'
    if not names:return 'empty'
    for side in ('l','r'):
        if names<={p+'_'+side for p in ('upperarm','forearm','hand')}:return 'arm.'+side
        if names<={p+'_'+side for p in ('thigh','calf','foot')}:return 'leg.'+side
    if names=={'chest'}:return 'torso'
    helpers=names-{'chest','pelvis'}
    def skirt(name):
        match=re.fullmatch(r'(.+-skirt_[0-9]+)_(upper|lower)',name)
        if not match:return False
        root=match[1];upper=bones.get(root+'_upper',{});lower=bones.get(root+'_lower',{})
        return (upper.get('parent')=='pelvis' and lower.get('parent')==root+'_upper'
                and all(math.isfinite(b.get('length',0)) and b.get('length',0)>0 for b in (upper,lower)))
    if helpers and all(skirt(n) for n in helpers):return 'garment_plane_candidate'
    return 'unmodeled'


def build(document):
    bones={b['name']:b for b in document['bones']};rows=[]
    if len(document['skins'])!=1:raise ValueError('surface_inventory_single_skin')
    for slot in document['slots']:
        mesh=document['skins'][0]['attachments'][slot['name']][slot['attachment']]
        names=influences(document,slot,mesh)
        rows.append(dict(slot=slot['name'],role=classify(names,bones),bones=sorted(names or []),
                         slot_bone=slot['bone']))
    return dict(profile='rendered-influence-surface-routing-v1-experiment',surfaces=rows,authority='none',selected=False,
                scope='model_eligibility_not_measured_surface_depth_or_semantic_approval')
