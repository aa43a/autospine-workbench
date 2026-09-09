"""Whole-region candidate selection using dense FK replay, never production adoption."""
from copy import deepcopy
import math
from .component_mesh_tracks import tracks
from .component_fk_qa import sample_track
from .component_local_solver import metrics
from .component_temporal_qa import passed
from ...resolved_project import canonical_sha256

PROFILE = 'whole-region-fk-129-nonregression-v1'


def gate(before, after):
    if len(before) != 129 or len(after) != 129:
        raise ValueError('distal_guard_tick_inventory')
    reasons = set(); improved = False
    for old, new in zip(before, after):
        for item in (old, new):
            if any(not math.isfinite(item[k]) for k in ('inversions', 'min_area_ratio', 'max_area_ratio', 'max_edge_stretch')):
                raise ValueError('distal_guard_nonfinite')
        if passed(old) and not passed(new): reasons.add('new_failed_tick')
        if new['inversions'] > old['inversions']: reasons.add('new_inversion')
        if len(new['bad_triangles']) > len(old['bad_triangles']): reasons.add('area_failure_count_increased')
        if new['max_edge_stretch'] > max(2., old['max_edge_stretch']) + 1e-9: reasons.add('edge_stretch_regression')
        improved |= (not passed(old) and passed(new) or new['inversions'] < old['inversions']
                     or len(new['bad_triangles']) < len(old['bad_triangles']))
    return sorted(reasons), improved


def inventory(rows):
    result = {(r['layer_id'], r['component_id']): r for r in rows}
    if len(result) != len(rows): raise ValueError('distal_guard_duplicate_region')
    return result


def build(old, trial, old_keys, trial_keys, skeleton):
    for document in (old, trial, old_keys, trial_keys):
        if (document.get('authority') != 'none' or document.get('production_authorized') is not False
                or document['project_id'] != old['project_id']
                or document['skeleton_sha256'] != canonical_sha256(skeleton)):
            raise ValueError('distal_guard_source_mismatch')
    if (old['schema'] != 'autospine.component-weight-transition/v1'
            or trial['schema'] != 'autospine.component-parent-distal/v1'
            or trial['source_sha256'] != canonical_sha256(old)):
        raise ValueError('distal_guard_weight_source_mismatch')
    for source, keys in ((old, old_keys), (trial, trial_keys)):
        if keys['schema'] != 'autospine.component-collar-keys/v1' or keys['source_sha256'] != canonical_sha256(source):
            raise ValueError('distal_guard_correction_source_mismatch')
    baseline, alternative = inventory(old['records']), inventory(trial['records'])
    poses, newposes = inventory(old_keys['rows']), inventory(trial_keys['rows'])
    if baseline.keys() != alternative.keys() or poses.keys() != newposes.keys() or not poses.keys() <= baseline.keys():
        raise ValueError('distal_guard_region_inventory')
    bones = {b['id']: b for b in skeleton['bones']}; records = []; rows = []; evidence = []
    for key, record in baseline.items():
        candidate = alternative[key]; mesh, newmesh = record['mesh'], candidate['mesh']
        for field in ('isolated_image_sha256', 'layer_id', 'component_id'):
            if record.get(field) != candidate.get(field): raise ValueError('distal_guard_geometry_mismatch')
        if mesh is not None and newmesh is not None:
            for field in ('vertices_xy', 'uvs', 'triangles', 'bone_ids', 'raster_qa'):
                if mesh[field] != newmesh[field]: raise ValueError('distal_guard_geometry_mismatch')
        elif mesh != newmesh: raise ValueError('distal_guard_geometry_mismatch')
        reasons = set(); improved = False; comparisons = []
        if key in poses:
            chain = [bones[b] for b in mesh['bone_ids']]
            a = tracks(mesh, skeleton, poses[key]['poses']); b = tracks(newmesh, skeleton, newposes[key]['poses'])
            if [(t['bone_id'], t['angles'], t['ids']) for t in a] != [(t['bone_id'], t['angles'], t['ids']) for t in b]:
                raise ValueError('distal_guard_track_inventory')
            for left, right in zip(a, b):
                before = []; after = []
                for tick in range(129):
                    before.append(metrics(mesh['vertices_xy'], sample_track(mesh, chain, left, tick/16, True), mesh['triangles']))
                    after.append(metrics(newmesh['vertices_xy'], sample_track(newmesh, chain, right, tick/16, True), newmesh['triangles']))
                rejected, gain = gate(before, after); reasons.update(rejected); improved |= gain
                comparisons.append(dict(bone_id=left['bone_id'], before=before, after=after, reason_codes=rejected))
        selected = not reasons and improved
        records.append(deepcopy(candidate if selected else record))
        if key in poses: rows.append(deepcopy(newposes[key] if selected else poses[key]))
        evidence.append(dict(layer_id=key[0], component_id=key[1], selected_trial=selected,
                             reason_codes=sorted(reasons) or (['sampled_improvement'] if selected else ['no_sampled_gain']),
                             comparisons=comparisons))
    return dict(schema='autospine.component-distal-guard/v1', profile=PROFILE, project_id=old['project_id'],
                sources={name: canonical_sha256(doc) for name, doc in
                         [('baseline', old), ('trial', trial), ('baseline_keys', old_keys), ('trial_keys', trial_keys)]},
                skeleton_sha256=canonical_sha256(skeleton), records=records, rows=rows, evidence=evidence,
                authority='none', production_authorized=False, runtime_status='not_evaluated', continuous_time_proven=False)
