"""Joint-collar candidates admitted only after per-track FK regression."""
from copy import deepcopy
from .component_collar_solver import solve
from .component_mesh_tracks import tracks
from .component_fk_qa import sample_track
from .component_temporal_qa import passed
from .component_local_solver import metrics
from ...resolved_project import canonical_sha256


def evaluate(mesh,chain,track):
    return [metrics(mesh['vertices_xy'],sample_track(mesh,chain,track,i/4,True),mesh['triangles']) for i in range(33)]


def build(source,correction,skeleton):
    if correction['source_sha256']!=canonical_sha256(source) or correction['skeleton_sha256']!=canonical_sha256(skeleton):
        raise ValueError('collar_source_mismatch')
    meshmap={(r['layer_id'],r['component_id']):r['mesh'] for r in source['records']}
    bones={b['id']:b for b in skeleton['bones']};result=deepcopy(correction);comparisons=[]
    for row in result['rows']:
        mesh=meshmap[row['layer_id'],row['component_id']];chain=[bones[b] for b in mesh['bone_ids']]
        byid={p['id']:p for p in row['poses']}
        for joint,track in enumerate(tracks(mesh,skeleton,row['poses'])):
            revised=deepcopy(track);evidence=[]
            for i,(original,initial) in enumerate(zip(track['original'],track['corrected'])):
                points,info=solve(mesh,original,initial,chain,joint)
                revised['corrected'][i]=points;evidence.append(info)
            before=evaluate(mesh,chain,track);after=evaluate(mesh,chain,revised)
            def score(q):return sum(not passed(p) for p in q),sum(p['inversions'] for p in q),sum(len(p['bad_triangles']) for p in q)
            a,b=score(after),score(before)
            accepted=(all(x<=y for x,y in zip(a,b)) and a!=b and
                      all(not passed(old) or passed(new) for old,new in zip(before,after)) and
                      all(new['inversions']<=old['inversions'] for old,new in zip(before,after)))
            if accepted:
                for identifier,points in zip(track['ids'],revised['corrected']):
                    byid[identifier]['points']=points
                    byid[identifier]['selected_qa']=metrics(mesh['vertices_xy'],points,mesh['triangles'])
            comparisons.append(dict(layer_id=row['layer_id'],component_id=row['component_id'],bone_id=track['bone_id'],
                selected=accepted,before=before,trial=after,score_before=list(b),score_after=list(a),evidence=evidence))
    for row in result['rows']:
        row['poses']=[{k:p[k] for k in ('id','points','selected_qa')} for p in row['poses']]
    # This is a new experiment envelope. The previous correction remains immutable.
    return dict(schema='autospine.component-collar/v1',profile='joint-local-rigid-collar-v1',
        source_sha256=canonical_sha256(source),correction_sha256=canonical_sha256(correction),skeleton_sha256=canonical_sha256(skeleton),
        project_id=source['project_id'],rows=result['rows'],comparisons=comparisons,authority='none',production_authorized=False,
        runtime_status='not_evaluated',continuous_time_proven=False)
