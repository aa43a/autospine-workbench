"""Refine only failing temporal samples of an exact shoulder boundary trial."""
from copy import deepcopy
from hashlib import sha256
import json
import math

from ...automation.storage_io import canonical_bytes
from ...asset.planning.component_local_solver import metrics
from .affine_pose import sample, matrices
from .deform_addition import entries, value, local_delta, add
from .numeric_reference import read
from .shoulder_source import contexts, select_rows
from .shoulder_boundary import prepare, solve
from .shoulder_boundary_candidate import finalize
from .skirt_candidate import inverse


def failures(files, original, prepared):
    reference = read(files); failures = {}
    setup = matrices(dict(original, animations={'setup': {}}), 'setup', 0)['chest']
    for name, frames in reference['animations'].items():
        for row, context, _ in prepared:
            slot = row['slot']; times = []
            local = [inverse(setup, row['points'][v]) for v in context['pins']]
            for frame in frames:
                points = frame['vertices'][slot]; q = metrics(row['points'], points, row['triangles'])
                a, b, c, d, x, y = matrices(original, name, frame['time'])['chest']
                pin_error = max(math.dist(points[v], (a*u+b*w+x, c*u+d*w+y))
                                for v, (u, w) in zip(context['pins'], local, strict=True))
                if q['bad_triangles'] or q['max_edge_stretch'] > 2 or pin_error > .5:
                    times.append(frame['time'])
            if times: failures[name, slot] = times
    return failures


def generate(files, source_digest, trial_files, trial_digest, *, progress=lambda message: None):
    prior = json.loads(trial_files['shoulder-boundary-trial.json'])
    if prior['profile'] != 'proximal-contact-pinned-shape-v1' or prior['source_character_sha256'] != source_digest:
        raise ValueError('shoulder_adaptive_trial_source_mismatch')
    original, rows = contexts(files); document = json.loads(trial_files['skeleton.json'])
    rows = select_rows(rows, sorted({r['slot'] for r in prior['records']}))
    if any(original[key] != document[key] for key in ('bones', 'slots', 'skins')):
        raise ValueError('shoulder_adaptive_unexpected_bind_change')
    prepared = [(r, prepare(r['points'], r['triangles'], r['contact'], r['root'], r['distal']),
                 entries(original['skins'][0]['attachments'][r['slot']][r['slot']])) for r in rows]
    records = deepcopy(prior['records']); solved = {}; correction = {}; original_keys = {}
    for record in records:
        name, slot = record['animation'], record['slot']; key = name, slot
        size = 2*sum(len(r) for r in entries(original['skins'][0]['attachments'][slot][slot]))
        old = original['animations'][name].get('attachments', {}).get('default', {}).get(slot, {}).get(slot, {}).get('deform', [])
        keys = document['animations'][name]['attachments']['default'][slot][slot]['deform']
        original_keys[key] = old
        correction[key] = {k['time']: [a-b for a, b in zip(value(keys, k['time'], size), value(old, k['time'], size))] for k in keys}
        duration = keys[-1]['time']; solved[key] = {duration*i/32 for i in range(33)}
    output = trial_files; history = []
    for iteration in range(3):
        bad = failures(output, original, prepared)
        if not bad: break
        progress(f'adaptive round {iteration+1}: {sum(map(len, bad.values()))} failing samples')
        added = 0
        for row, context, influences in prepared:
            slot = row['slot']; size = 2*sum(len(r) for r in influences)
            for name in original['animations']:
                key = name, slot; times = [t for t in bad.get(key, []) if t not in solved[key]]
                if len(solved[key])+len(times) > 257: raise ValueError('shoulder_adaptive_sample_budget')
                record = next(r for r in records if (r['animation'], r['slot']) == key)
                for time in times:
                    progress(f'{name}: {slot} refine {time}')
                    world = sample(original, name, time)[0][slot]
                    corrected, evidence = solve(original, name, time, row['points'], row['triangles'], world, context)
                    record['max_displacement_px'] = max(record['max_displacement_px'], evidence['displacement_from_original_px'])
                    quality = evidence['geometry']
                    if quality['bad_triangles'] or quality['max_edge_stretch'] > 2 or not evidence['within_budget']:
                        record['solver_failures'].append(dict(time=time, geometry=quality, within_budget=evidence['within_budget']))
                    correction[key][time] = local_delta(original, influences, matrices(original, name, time), world, corrected)
                    solved[key].add(time); added += 1
                keys = [dict(time=t, vertices=v) for t, v in sorted(correction[key].items())]
                combined = add(original_keys[key], keys, size)
                document['animations'][name]['attachments']['default'][slot][slot]['deform'] = combined
                record.update(correction_key_count=len(solved[key]), total_key_count=len(combined))
        history.append(dict(round=iteration+1, failing_samples=sum(map(len, bad.values())), added_keys=added))
        output, report = finalize(files, original, document, prepared, records, source_digest, progress=progress,
                                  profile='proximal-contact-pinned-shape-adaptive-v2')
        if not added: break
    if not history:
        output, report = finalize(files, original, document, prepared, records, source_digest,
                                  profile='proximal-contact-pinned-shape-adaptive-v2')
    report.update(adaptive_history=history, source_trial_sha256=trial_digest)
    output['shoulder-boundary-trial.json'] = canonical_bytes(report)
    manifest = json.loads(output['character-manifest.json'])
    manifest['files'] = {n: sha256(raw).hexdigest() for n, raw in output.items() if n != 'character-manifest.json'}
    output['character-manifest.json'] = canonical_bytes(manifest)
    return output, report
