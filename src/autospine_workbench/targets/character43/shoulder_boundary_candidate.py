"""Bake an isolated proximal boundary trial into the complete source character."""
from copy import deepcopy
from hashlib import sha256
import json
import math

from ...automation.storage_io import canonical_bytes
from .affine_pose import sample, matrices
from .deformation_qa import inspect
from .numeric_reference import read, write
from .shoulder_source import contexts, select_rows
from .shoulder_boundary import prepare, solve
from .skirt_candidate import inverse
from .deform_addition import entries, local_delta, add


def generate(files, source_digest, *, slot_ids=None, progress=lambda message: None):
    inspect(files)
    original, rows = contexts(files); document = deepcopy(original)
    rows = select_rows(rows, slot_ids)
    source_reference = read(files); records = []; prepared = []
    for row in rows:
        if not row['contact']: raise ValueError('shoulder_boundary_contact_missing')
        context = prepare(row['points'], row['triangles'], row['contact'], row['root'], row['distal'])
        influences = entries(original['skins'][0]['attachments'][row['slot']][row['slot']])
        prepared.append((row, context, influences))
    if not prepared: raise ValueError('shoulder_boundary_no_regions')
    for name, animation in original['animations'].items():
        duration = source_reference['animations'][name][-1]['time']
        for row, context, influences in prepared:
            slot = row['slot']; keys = []; failures = []; maximum = 0.
            progress(f'{name}: {slot}')
            old_keys = animation.get('attachments', {}).get('default', {}).get(slot, {}).get(slot, {}).get('deform', [])
            if old_keys and old_keys[0]['time'] != 0: raise ValueError('shoulder_deform_start_unsupported')
            for i in range(33):
                time = duration*i/32; world = sample(original, name, time)[0][slot]
                if max(math.dist(a, b) for a, b in zip(world, row['points'], strict=True)) < 1e-8:
                    corrected = world
                else:
                    corrected, evidence = solve(original, name, time, row['points'], row['triangles'], world, context)
                    quality = evidence['geometry']
                    if quality['bad_triangles'] or quality['max_edge_stretch'] > 2 or not evidence['within_budget']:
                        failures.append(dict(time=time, geometry=quality, within_budget=evidence['within_budget']))
                maximum = max(maximum, max(math.dist(a, b) for a, b in zip(world, corrected, strict=True)))
                delta = local_delta(original, influences, matrices(original, name, time), world, corrected)
                keys.append(dict(time=time, vertices=delta))
            combined = add(old_keys, keys, 2*sum(len(r) for r in influences))
            target = document['animations'][name].setdefault('attachments', {}).setdefault('default', {})
            target.setdefault(slot, {}).setdefault(slot, {})['deform'] = combined
            records.append(dict(animation=name, slot=slot, context=context, solver_failures=failures,
                                correction_key_count=len(keys), total_key_count=len(combined),
                                max_displacement_px=maximum))
    return finalize(files, original, document, prepared, records, source_digest, progress=progress)


def finalize(files, original, document, prepared, records, source_digest, *, progress=lambda message: None,
             profile='proximal-contact-pinned-shape-v1'):
    source_reference = read(files)
    selected = {row['slot'] for row, _, _ in prepared}
    setup_matrices = matrices(dict(original, animations={'setup': {}}), 'setup', 0)
    reference = dict(skeleton_sha256='', animations={}); boundary = []; unselected_error = 0.; fixed_error = 0.
    maxima = {(r['animation'], r['slot']): 0. for r in records}
    for name, frames in source_reference['animations'].items():
        progress(f'{name}: dense validation')
        key_times = {k['time'] for slot in selected for k in document['animations'][name]['attachments']['default'][slot][slot]['deform']}
        times = sorted(key_times | {f['time'] for f in frames})
        times = sorted(set(times) | {(a+b)/2 for a, b in zip(times, times[1:])})
        reference['animations'][name] = []; max_pin = 0.; before_pin = 0.; max_move = 0.
        for time in times:
            before = sample(original, name, time)[0]; after = sample(document, name, time)[0]
            unselected_error = max(unselected_error, max(math.dist(a, b) for slot in before if slot not in selected
                for a, b in zip(before[slot], after[slot], strict=True)))
            matrix = matrices(original, name, time)['chest']; a, b, c, d, x, y = matrix
            for row, context, _ in prepared:
                slot = row['slot']; movable = set(context['pins']+context['free'])
                for vertex, (old, new) in enumerate(zip(before[slot], after[slot], strict=True)):
                    distance = math.dist(old, new); max_move = max(max_move, distance/context['budget_px'])
                    maxima[name, slot] = max(maxima[name, slot], distance)
                    if vertex not in movable: fixed_error = max(fixed_error, distance)
                for vertex in context['pins']:
                    u, v = inverse(setup_matrices['chest'], row['points'][vertex])
                    target = (a*u+b*v+x, c*u+d*v+y)
                    max_pin = max(max_pin, math.dist(target, after[slot][vertex]))
                    before_pin = max(before_pin, math.dist(target, before[slot][vertex]))
            reference['animations'][name].append(dict(time=time, vertices=after))
        boundary.append(dict(animation=name, frames=len(times), max_pin_error_px=max_pin,
                             original_pin_error_px=before_pin, max_displacement_budget_ratio=max_move))
    if unselected_error > 1e-7 or fixed_error > 1e-7: raise ValueError('shoulder_boundary_unselected_motion_changed')
    for record in records:
        record['max_displacement_px'] = maxima[record['animation'], record['slot']]
        record['displacement_scope'] = 'all_dense_validation_frames'
    output = dict(files); output['skeleton.json'] = canonical_bytes(document)
    if 'editor/skeleton.json' in files:
        editor = json.loads(files['editor/skeleton.json'])
        editor.update({k: document[k] for k in ('bones', 'slots', 'skins', 'animations')})
        output['editor/skeleton.json'] = canonical_bytes(editor)
    reference['skeleton_sha256'] = sha256(output['skeleton.json']).hexdigest()
    output = write(output, reference); qa = inspect(output)
    output['deformation.json'] = canonical_bytes(qa)
    passed = qa['passed'] and all(not r['solver_failures'] for r in records) and all(
        r['max_pin_error_px'] <= .5 and r['max_displacement_budget_ratio'] <= 1+1e-7 for r in boundary)
    report = dict(profile=profile, authority='none', selected=False,
                  source_character_sha256=source_digest, status='needs_review' if passed else 'blocked',
                  geometry_passed=qa['passed'], records=records, dense_boundary=boundary,
                  unselected_error_px=unselected_error, distal_fixed_error_px=fixed_error,
                  runtime_status='not_run', visual_contact_status='not_evaluated',
                  scope='sampled_boundary_and_geometry_not_continuous_or_raster_proof')
    output['shoulder-boundary-trial.json'] = canonical_bytes(report)
    manifest = json.loads(files['character-manifest.json'])
    manifest.update(profile='whole-character-shoulder-boundary-trial-v1', authority='none',
                    production_authorized=False, full_character_animation=False, status=report['status'],
                    qa=dict(runtime_status='not_run', full_character_contact_status='not_evaluated'))
    manifest['files'] = {n: sha256(raw).hexdigest() for n, raw in output.items() if n != 'character-manifest.json'}
    output['character-manifest.json'] = canonical_bytes(manifest)
    return output, report
