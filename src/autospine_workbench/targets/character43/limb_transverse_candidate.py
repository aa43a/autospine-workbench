"""Isolated transverse-frame candidate followed by additive joint correction."""
from copy import deepcopy
from hashlib import sha256
import json

from ...automation.storage_io import canonical_bytes
from .affine_pose import sample
from .deformation_qa import inspect
from .final_motion_contact import recheck
from .fixed_area_feasibility import FixedAreaInfeasible
from .limb_transverse_repair import build as compensate, PROFILE
from .numeric_reference import read, write, carry_setup
from .projected_area_adaptive import build as correct_joints


def build(files, slots, name='external-motion', on_progress=None):
    document = json.loads(files['skeleton.json']); parent = read(files)
    identity = sha256(files['skeleton.json']).hexdigest()
    setup = json.loads(files['rig-setup-reference.json'])
    if parent['skeleton_sha256'] != identity or setup['skeleton_sha256'] != identity:
        raise ValueError('limb_transverse_source_mismatch')
    review = json.loads(files['motion-review.json'])
    if review.get('source_pose_fit', {}).get('profile') != 'source-absolute-limb-projection-v1':
        raise ValueError('limb_transverse_source_projection_required')
    if set(document['animations']) != {name}:
        raise ValueError('limb_transverse_single_animation_required')
    if on_progress:on_progress(dict(stage='compensate_transverse'))
    transverse, evidence = compensate(document, name, slots)
    result = deepcopy(document)
    target = result['animations'][name].setdefault('attachments', {}).setdefault('default', {})
    corrections = []
    for slot in slots:
        isolated = deepcopy(transverse)
        isolated['slots'] = [s for s in isolated['slots'] if s['name'] == slot]
        isolated['skins'][0]['attachments'] = {slot: isolated['skins'][0]['attachments'][slot]}
        isolated['animations'][name]['attachments']['default'] = {
            slot: isolated['animations'][name]['attachments']['default'][slot]}
        blocker = None
        try:
            solved, correction = correct_joints(isolated, name, {slot: setup['vertices'][slot]},
                temporal=True, additive=True, dual_floor=True, progress=on_progress)
        except FixedAreaInfeasible as error:
            # Keep the counterexample and original production geometry gate.
            # The projected solve only makes a diagnostic comparison possible;
            # it does not grant support to unavoidable setup-area compression.
            blocker = error.report
            solved, correction = correct_joints(isolated, name, {slot: setup['vertices'][slot]},
                temporal=True, additive=True, progress=on_progress)
        target[slot] = solved['animations'][name]['attachments']['default'][slot]
        corrections.append(dict(slot=slot, solver=correction, fixed_area_blocker=blocker,
            validation='projected_only_diagnostic' if blocker else 'setup_and_projected_area'))
    restored = deepcopy(result)
    for slot in slots:
        previous = document['animations'][name].get('attachments', {}).get('default', {}).get(slot)
        if previous is None:del restored['animations'][name]['attachments']['default'][slot]
        else:restored['animations'][name]['attachments']['default'][slot] = previous
    # Compare the entire non-attachment animation and bind, as well as every
    # unselected attachment; new frame correction cannot change joint motion.
    if any(result[k] != document[k] for k in ('bones', 'slots', 'skins')):
        raise ValueError('limb_transverse_bind_changed')
    before_animation = deepcopy(document['animations'][name]); after_animation = deepcopy(restored['animations'][name])
    for animation in (before_animation, after_animation):
        for skin in list(animation.get('attachments', {})):
            if not animation['attachments'][skin]:del animation['attachments'][skin]
        if not animation.get('attachments'):animation.pop('attachments', None)
    if after_animation != before_animation:
        raise ValueError('limb_transverse_unrelated_channels_changed')
    from ...automation.motion_target_pose import final_times
    midpoints = final_times(result, name, [])
    times = sorted(set(final_times(result, name, midpoints)) |
                   {f['time'] for f in parent['animations'][name]})
    if len(times) > 4097:raise ValueError('limb_transverse_sample_limit')
    output = {n: v for n, v in files.items() if n.endswith('.png') or n in ('skeleton.atlas', 'motion-ir.json')}
    output['skeleton.json'] = canonical_bytes(result); carry_setup(files, output)
    digest = sha256(output['skeleton.json']).hexdigest()
    frames = []; old_frames = []
    for i, time in enumerate(times):
        if on_progress and i % 64 == 0:on_progress(dict(stage='validate', index=i, total=len(times)))
        frames.append(dict(time=time, vertices=sample(result, name, time)[0]))
        old_frames.append(dict(time=time, vertices=sample(document, name, time)[0]))
    output = write(output, dict(skeleton_sha256=digest, animations={name: frames}), compressed=True)
    baseline = write({'skeleton.json': files['skeleton.json']},
                     dict(skeleton_sha256=identity, animations={name: old_frames}), compressed=True)
    before = inspect(baseline, setup_vertices=setup['vertices'])
    geometry = inspect(output, setup_vertices=setup['vertices'])
    contact = recheck(result, name, json.loads(files['motion-ir.json']),
                      json.loads(files['motion-contact.json']), times, review['reference_length_px'])
    review.update(status='needs_changes', geometry_passed=geometry['passed'],
        contact_status=contact['status'], runtime_status='not_evaluated', depth_order_status='not_evaluated',
        authority='none', selected=False, production_authorized=False)
    review['issues'] = [i for i in review.get('issues', []) if i['stage'] == 'projection']
    review['issues'].append(dict(stage='repair', reason_code='motion_repair_requires_visual_and_depth_revalidation'))
    if not geometry['passed']:
        review['issues'].append(dict(stage='geometry', reason_code='motion_target_deformation_needs_changes'))
    for key in ('area_repair', 'post_contact_repair'):review.pop(key, None)
    report = dict(profile=PROFILE, source_skeleton_sha256=identity, skeleton_sha256=digest,
        transverse=evidence, joint_corrections=corrections, parent_geometry=before, geometry=geometry,
        sample_count=len(times), selected=False, authority='none', production_authorized=False,
        scope='same_grid_transverse_candidate_original_geometry_gate_retained',
        contact_status=contact['status'], runtime_status='not_evaluated', visual_status='not_reviewed')
    output.update({'motion-transverse.json': canonical_bytes(report),
        'motion-review.json': canonical_bytes(review), 'parent-motion-review.json': files['motion-review.json'],
        'motion-contact.json': canonical_bytes(contact), 'deformation.json': canonical_bytes(geometry)})
    manifest = json.loads(files['character-manifest.json'])
    manifest.update(status='needs_changes', authority='none', selected=False, production_authorized=False,
                    files={n: sha256(v).hexdigest() for n, v in output.items()})
    output['character-manifest.json'] = canonical_bytes(manifest)
    return output, report
