"""One declared garment, fresh full-character QA, no inherited quality approval."""
from copy import deepcopy
from hashlib import sha256
import json

from ...automation.storage_io import canonical_bytes
from ...automation.motion_target_pose import final_times
from .attachment_root_bake import build as bake
from .affine_pose import sample
from .deformation_qa import inspect
from .numeric_reference import carry_setup, read, write
from .garment_follow_scope import PROFILE, STABLE_TIME_POLICY, resolve


def build(files, character, plan, on_progress=None):
    slot, name = plan['slot'], plan['animation']
    stable_sampling = plan['garment_follow'].get('time_policy') == STABLE_TIME_POLICY
    declaration = resolve(files, character, slot, name, stable_sampling=stable_sampling)
    frozen = {k: v for k, v in plan['garment_follow'].items() if k != 'character_sha256'}
    if declaration != frozen:
        raise ValueError('motion_garment_scope_changed')
    document = json.loads(files['skeleton.json']); reference = read(files)
    original_times = [r['time'] for r in reference['animations'][name]]
    bake_times = final_times(document, name, [] if stable_sampling else original_times)
    result, report = bake(document, name, json.loads(files['motion-torso-projection.json']),
                          declaration['roots'], bake_times, on_progress)
    if report['rows'] != [dict(slot=slot)]:
        raise ValueError('motion_garment_affected_scope_changed')
    restored = deepcopy(result)
    previous = document['animations'][name].get('attachments', {}).get('default', {}).get(slot)
    tracks = restored['animations'][name]['attachments']['default']
    if previous is None:
        del tracks[slot]
        if not tracks: del restored['animations'][name]['attachments']['default']
        if not restored['animations'][name]['attachments']: del restored['animations'][name]['attachments']
    else:
        tracks[slot] = previous
    if restored != document: raise ValueError('motion_garment_unrelated_channels_changed')
    times = final_times(result, name, [] if stable_sampling else original_times)
    if stable_sampling:
        times = sorted(set(times) | set(original_times))
        if len(times) > 4097: raise ValueError('source_pose_final_sample_limit')
    output = {n: v for n, v in files.items()
              if n.endswith('.png') or n in ('skeleton.atlas', 'motion-ir.json', 'motion-torso-projection.json')}
    output['skeleton.json'] = canonical_bytes(result)
    setup = carry_setup(files, output)
    if setup is None: raise ValueError('motion_garment_setup_required')
    frames = []; before = []
    for index, time in enumerate(times):
        if on_progress and index % 32 == 0:
            on_progress(dict(stage='validate', index=index, total=len(times)))
        frames.append(dict(time=time, vertices=sample(result, name, time)[0]))
        before.append(dict(time=time, vertices=sample(document, name, time)[0]))
    output = write(output, dict(skeleton_sha256=sha256(output['skeleton.json']).hexdigest(), animations={name: frames}), compressed=True)
    baseline = write(dict(files), dict(skeleton_sha256=sha256(files['skeleton.json']).hexdigest(), animations={name: before}))
    geometry = inspect(output, setup_vertices=setup)
    parent_geometry = inspect(baseline, setup_vertices=setup)
    from .garment_follow_contact import anchors, measure
    waist = dict(status='unavailable', raster_status='not_evaluated')
    try:
        pairs = anchors(character, files, slot)
        waist.update(status='measured', anchors=len(pairs), sample_count=len(times),
                     before=measure(before, slot, pairs), after=measure(frames, slot, pairs))
    except (ValueError, KeyError, IndexError):
        waist['reason_code'] = 'motion_garment_contact_unobservable'
    from .final_motion_contact import recheck
    old = json.loads(files['motion-review.json'])
    contact = recheck(result, name, json.loads(files['motion-ir.json']),
                      json.loads(files['motion-contact.json']), times, old['reference_length_px'])
    evidence = dict(status='needs_changes', reference_length_px=old['reference_length_px'],
        geometry_passed=geometry['passed'], runtime_status='not_evaluated', depth_order_status='not_evaluated',
        contact_status=contact['status'], authority='none', selected=False, production_authorized=False,
        issues=[i for i in old.get('issues', []) if i['stage'] == 'projection'])
    for key in ('source_pose_fit', 'projected_lengths'):
        if key in old: evidence[key] = old[key]
    evidence['issues'].append(dict(stage='repair', reason_code='motion_garment_requires_runtime_and_visual_review'))
    if not geometry['passed']:
        evidence['issues'].append(dict(stage='geometry', reason_code='motion_target_deformation_needs_changes'))
    report.update(declaration=plan['garment_follow'], waist_contact=waist, validation_sample_count=len(times))
    output.update({'deformation.json': canonical_bytes(geometry), 'motion-review.json': canonical_bytes(evidence),
        'motion-contact.json': canonical_bytes(contact), 'parent-motion-review.json': files['motion-review.json'],
        'motion-garment-follow.json': canonical_bytes(report)})
    output['motion-repair.json'] = canonical_bytes(dict(profile=PROFILE, slot=slot, animation=name,
        parent_geometry=parent_geometry, geometry=geometry, garment_follow=report,
        unchanged_other_channels=True, authority='none', selected=False, sample_count=len(times),
        scope='same_grid_whole_character_samples_not_visual_acceptance'))
    manifest = json.loads(files['character-manifest.json'])
    manifest.update(status='needs_changes', authority='none', selected=False, production_authorized=False,
                    files={n: sha256(v).hexdigest() for n, v in output.items()})
    output['character-manifest.json'] = canonical_bytes(manifest)
    return output, evidence, geometry
