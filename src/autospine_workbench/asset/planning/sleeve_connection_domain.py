"""Role-bounded cloth connection freedom; hand and unknown remain fixed."""
from collections import defaultdict
from copy import deepcopy
from .component_distal_guard import inventory,gate
from ...resolved_project import canonical_sha256


def domain(triangles,assignments):
    if len(triangles)!=len(assignments):raise ValueError('sleeve_connection_inventory')
    roles=defaultdict(set);neighbors=defaultdict(set)
    for tri,item in zip(triangles,assignments):
        for i in tri:roles[i].add(item['role']);neighbors[i].update(set(tri)-{i})
    allowed={'sleeve','cuff','hanging_cloth'}
    protected={i for i,r in roles.items() if not r<=allowed}
    seeds={i for i,r in roles.items() if 'hanging_cloth' in r or 'cuff' in r}
    # One topological ring connects interior cloth to adjacent sleeve support.
    support=seeds|{j for i in seeds for j in neighbors[i]}
    free=sorted(support-protected)
    return dict(profile='garment-connection-ring1-v1',free_vertices=free,
        anchors=sorted(set(roles)-set(free)),protected_vertices=sorted(protected),
        vertex_roles={str(i):sorted(r) for i,r in roles.items()},
        shared_topology='unchanged',texture='unchanged')


def prepare(source,garment,draft):
    if (source['schema']!='autospine.cloth-anchor-correction/v1'
            or garment['schema']!='autospine.sleeve-weights/v1'
            or garment['draft_sha256']!=canonical_sha256(draft)
            or any(d.get('authority')!='none' or d.get('production_authorized') is not False for d in (source,garment,draft))
            or garment['project_id']!=source['project_id']):raise ValueError('sleeve_connection_source')
    labels={(r['layer_id'],r['component_id']):r for r in draft['records']}
    meshes={(r['layer_id'],r['component_id']):r for r in garment['records']}
    result={}
    for row in source['records']:
        if 'helper' not in row:continue
        key=row['layer_id'],row['component_id'];mesh=meshes[key]['mesh']
        if mesh['triangles']!=row['triangles'] or mesh['vertices_xy']!=row['setup_vertices']:raise ValueError('sleeve_connection_geometry')
        result[key]=domain(row['triangles'],labels[key]['assignments'])
    return result


def retain(trial,baseline):
    if any(d.get('authority')!='none' or d.get('production_authorized') is not False for d in (trial,baseline)):
        raise ValueError('sleeve_connection_authority')
    if any(trial[k]!=baseline[k] for k in ('schema','source_sha256','skeleton_sha256','project_id')):
        raise ValueError('sleeve_connection_baseline')
    old=inventory(baseline['records']);new=inventory(trial['records'])
    if old.keys()!=new.keys():raise ValueError('sleeve_connection_inventory')
    result=deepcopy(trial);rows=[]
    for key,row in new.items():
        if 'tracks' not in row:rows.append(deepcopy(row));continue
        before=old[key];reasons=[];gain=False
        if len(row['tracks'])!=len(before['tracks']):raise ValueError('sleeve_connection_track_inventory')
        for a,b in zip(before['tracks'],row['tracks']):
            if a['bone_id']!=b['bone_id'] or a['amplitudes']!=b['amplitudes']:raise ValueError('sleeve_connection_track_identity')
            rejected,improved=gate(a['qa'],b['qa']);reasons.extend(rejected);gain|=improved
        selected=not reasons and gain;chosen=deepcopy(row if selected else before)
        chosen['connection_trial']=dict(selected=selected,reason_codes=sorted(set(reasons)) or ['sampled_improvement' if selected else 'no_sampled_gain'],
            baseline_failed_ticks=[t['failed_ticks'] for t in before['tracks']],trial_failed_ticks=[t['failed_ticks'] for t in row['tracks']],
            trial_domain=row['correction_domain'])
        rows.append(chosen)
    result.update(records=rows,baseline_sha256=canonical_sha256(baseline))
    return result
