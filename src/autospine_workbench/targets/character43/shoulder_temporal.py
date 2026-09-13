"""Continue a failed shoulder clip along one local shape branch, without changing good clips."""
from copy import deepcopy
from hashlib import sha256
import json
import math

from ...automation.storage_io import canonical_bytes
from .affine_pose import sample, matrices
from .deform_addition import entries, local_delta, add
from .numeric_reference import read
from .shoulder_source import contexts, select_rows
from .shoulder_boundary import prepare, solve
from .shoulder_boundary_candidate import finalize
from .shoulder_boundary_adaptive import failures


def generate(files, source_digest, trial_files, trial_digest, *, progress=lambda message: None):
    prior = json.loads(trial_files['shoulder-boundary-trial.json'])
    if prior['profile'] != 'proximal-contact-pinned-shape-adaptive-v2' or prior['source_character_sha256'] != source_digest:
        raise ValueError('shoulder_temporal_trial_source_mismatch')
    original, rows = contexts(files); document = json.loads(trial_files['skeleton.json'])
    rows = select_rows(rows, sorted({r['slot'] for r in prior['records']}))
    if any(original[key] != document[key] for key in ('bones', 'slots', 'skins')):
        raise ValueError('shoulder_temporal_bind_change')
    prepared = [(r, prepare(r['points'], r['triangles'], r['contact'], r['root'], r['distal']),
                 entries(original['skins'][0]['attachments'][r['slot']][r['slot']])) for r in rows]
    selected = failures(trial_files, original, prepared)
    if not selected: raise ValueError('shoulder_temporal_no_failing_clips')
    records = deepcopy(prior['records']); reference = read(files); times = {}
    for (name, slot), failed_times in selected.items():
        duration = reference['animations'][name][-1]['time']
        bone_times = {k['time'] for tracks in original['animations'][name].get('bones', {}).values()
                      for keys in tracks.values() for k in keys}
        times[name, slot] = {duration*i/32 for i in range(33)} | bone_times | set(failed_times)
    output = trial_files; history = []
    for iteration in range(3):
        for (name, slot), key_times in times.items():
            if len(key_times) > 257: raise ValueError('shoulder_temporal_sample_budget')
            row, context, influences = next(p for p in prepared if p[0]['slot'] == slot)
            record = next(r for r in records if (r['animation'], r['slot']) == (name, slot))
            record['solver_failures'] = []; correction = []; previous = None
            progress(f'temporal round {iteration+1}: {name} {slot}, {len(key_times)} keys')
            for time in sorted(key_times):
                world = sample(original, name, time)[0][slot]
                if max(math.dist(a, b) for a, b in zip(world, row['points'], strict=True)) < 1e-8:
                    corrected = world
                else:
                    corrected, evidence = solve(original, name, time, row['points'], row['triangles'], world, context, previous=previous)
                    quality = evidence['geometry']
                    if quality['bad_triangles'] or quality['max_edge_stretch'] > 2 or not evidence['within_budget']:
                        record['solver_failures'].append(dict(time=time, geometry=quality, within_budget=evidence['within_budget']))
                previous = corrected
                correction.append(dict(time=time, vertices=local_delta(original, influences, matrices(original, name, time), world, corrected)))
            old = original['animations'][name].get('attachments', {}).get('default', {}).get(slot, {}).get(slot, {}).get('deform', [])
            combined = add(old, correction, 2*sum(len(r) for r in influences))
            document['animations'][name]['attachments']['default'][slot][slot]['deform'] = combined
            record.update(correction_key_count=len(correction), total_key_count=len(combined),
                          continuation='previous_corrected_world_pose_with_interval_area_constraint')
        output, report = finalize(files, original, document, prepared, records, source_digest, progress=progress,
                                  profile='proximal-contact-temporal-shape-v3')
        bad = failures(output, original, prepared)
        history.append(dict(round=iteration+1, failing_samples=sum(map(len, bad.values())),
                            solved_keys=sum(map(len, times.values()))))
        if not bad: break
        added = 0
        for key, failed_times in bad.items():
            if key not in times: raise ValueError('shoulder_temporal_unselected_regression')
            added += len(set(failed_times)-times[key]); times[key].update(failed_times)
        if not added: break
    # Rebuilding a failed clip cannot modify other existing candidate deforms.
    for name, animation in json.loads(trial_files['skeleton.json'])['animations'].items():
        for slot in document['skins'][0]['attachments']:
            if (name, slot) in selected: continue
            a = animation.get('attachments', {}).get('default', {}).get(slot)
            b = document['animations'][name].get('attachments', {}).get('default', {}).get(slot)
            if a != b: raise ValueError('shoulder_temporal_good_clip_changed')
    report.update(temporal_history=history, source_trial_sha256=trial_digest,
                  rebuilt_clips=[dict(animation=n, slot=s) for n, s in sorted(selected)],
                  interval_scope='linear_world_constraint_plus_dense_spine_samples_not_continuous_proof')
    output['shoulder-boundary-trial.json'] = canonical_bytes(report)
    manifest = json.loads(output['character-manifest.json'])
    manifest['files'] = {n: sha256(raw).hexdigest() for n, raw in output.items() if n != 'character-manifest.json'}
    output['character-manifest.json'] = canonical_bytes(manifest)
    return output, report
