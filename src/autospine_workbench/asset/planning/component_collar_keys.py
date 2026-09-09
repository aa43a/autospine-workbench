"""Individually admit corrective keys only after replaying their whole FK track."""
from copy import deepcopy
from .component_collar import evaluate
from .component_collar_solver import solve
from .component_mesh_tracks import tracks
from .component_temporal_qa import passed
from .component_local_solver import metrics
from ...resolved_project import canonical_sha256


def score(q):
    return [sum(not passed(p) for p in q),sum(p['inversions'] for p in q),sum(len(p['bad_triangles']) for p in q)]


def admission(before,after):
    failures=[i/4 for i,(old,new) in enumerate(zip(before,after)) if passed(old) and not passed(new)]
    inversions=[i/4 for i,(old,new) in enumerate(zip(before,after)) if new['inversions']>old['inversions']]
    a,b=score(after),score(before)
    return (not failures and not inversions and a!=b and all(x<=y for x,y in zip(a,b))),failures,inversions


def build(source,collar,skeleton):
    if (collar['schema']!='autospine.component-collar/v1' or collar['source_sha256']!=canonical_sha256(source)
            or collar['skeleton_sha256']!=canonical_sha256(skeleton)):
        raise ValueError('collar_keys_source_mismatch')
    result=deepcopy(collar['rows']);meshes={(r['layer_id'],r['component_id']):r['mesh'] for r in source['records']}
    bones={b['id']:b for b in skeleton['bones']};comparisons=[]
    for row in result:
        mesh=meshes[row['layer_id'],row['component_id']];chain=[bones[b] for b in mesh['bone_ids']]
        byid={p['id']:p for p in row['poses']}
        for joint,track in enumerate(tracks(mesh,skeleton,row['poses'])):
            before=evaluate(mesh,chain,track);current=before;trials=[]
            # Fixed near-setup-first order, independent of project name or observed failures.
            for i in sorted(range(9),key=lambda i:(abs(track['angles'][i]),track['angles'][i])):
                points,evidence=solve(mesh,track['original'][i],track['corrected'][i],chain,joint)
                if points==track['corrected'][i]:continue
                trial=deepcopy(track);trial['corrected'][i]=points
                qa=evaluate(mesh,chain,trial);ok,failures,inversions=admission(current,qa)
                trials.append(dict(key_id=track['ids'][i],selected=ok,score_before=score(current),score_trial=score(qa),
                                   new_failure_times=failures,new_inversion_times=inversions,evidence=evidence))
                if ok:
                    track=trial;current=qa
                    byid[track['ids'][i]]['points']=points
                    byid[track['ids'][i]]['selected_qa']=metrics(mesh['vertices_xy'],points,mesh['triangles'])
            comparisons.append(dict(layer_id=row['layer_id'],component_id=row['component_id'],bone_id=track['bone_id'],
                                    before=before,after=current,trials=trials))
    return dict(schema='autospine.component-collar-keys/v1',profile='near-setup-first-key-regression-v1',
                source_sha256=canonical_sha256(source),collar_sha256=canonical_sha256(collar),skeleton_sha256=canonical_sha256(skeleton),
                project_id=source['project_id'],rows=result,comparisons=comparisons,authority='none',production_authorized=False,
                runtime_status='not_evaluated',continuous_time_proven=False)
