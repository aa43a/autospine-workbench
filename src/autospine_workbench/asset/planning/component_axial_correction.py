"""Axial-band corrective hypotheses with dense per-key regression protection."""
from copy import deepcopy
from .component_axial_solver import solve
from .component_mesh_tracks import tracks
from .component_fk_qa import sample_track
from .component_local_solver import metrics
from .component_distal_guard import gate, inventory
from ...resolved_project import canonical_sha256


def evaluate(mesh, chain, track):
    return [metrics(mesh['vertices_xy'], sample_track(mesh, chain, track, i/16, True), mesh['triangles']) for i in range(129)]


def build(source, skeleton):
    if (source['schema'] != 'autospine.component-distal-guard/v1' or source.get('authority') != 'none'
            or source.get('production_authorized') is not False or source['skeleton_sha256'] != canonical_sha256(skeleton)):
        raise ValueError('axial_source_mismatch')
    rows = deepcopy(source['rows']); meshes = inventory(source['records'])
    bones = {b['id']: b for b in skeleton['bones']}; evidence = []
    for row in rows:
        mesh = meshes[row['layer_id'], row['component_id']]['mesh']
        if len(mesh['bone_ids']) != 3: continue
        chain = [bones[b] for b in mesh['bone_ids']]
        track = tracks(mesh, skeleton, row['poses'])[2]
        before = evaluate(mesh, chain, track); current = before; trials = []
        byid = {p['id']: p for p in row['poses']}
        for i in sorted(range(9), key=lambda i: (abs(track['angles'][i]), track['angles'][i])):
            points, info = solve(mesh, track['original'][i], track['corrected'][i], chain, 2)
            attempt = dict(key_id=track['ids'][i], solver=info, selected=False, reason_codes=['no_local_gain'])
            if points != track['corrected'][i]:
                trial = deepcopy(track); trial['corrected'][i] = points
                qa = evaluate(mesh, chain, trial); reasons, gain = gate(current, qa)
                attempt.update(reason_codes=reasons or (['sampled_improvement'] if gain else ['no_dense_gain']))
                if not reasons and gain:
                    attempt['selected'] = True; track = trial; current = qa
                    byid[track['ids'][i]]['points'] = points
                    byid[track['ids'][i]]['selected_qa'] = metrics(mesh['vertices_xy'], points, mesh['triangles'])
            trials.append(attempt)
        evidence.append(dict(layer_id=row['layer_id'], component_id=row['component_id'], bone_id=track['bone_id'],
                             before=before, after=current, trials=trials))
    return dict(schema='autospine.component-axial-correction/v1', profile='distal-axial-band-budget15-dense129-v1',
                project_id=source['project_id'], source_sha256=canonical_sha256(source), skeleton_sha256=canonical_sha256(skeleton),
                records=deepcopy(source['records']), rows=rows, evidence=evidence,
                authority='none', production_authorized=False, runtime_status='not_evaluated', continuous_time_proven=False)
