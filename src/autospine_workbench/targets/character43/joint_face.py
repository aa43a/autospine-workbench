"""Bake isolated facial controls into ordinary Spine bones and slot timelines.

No browser effect or replacement raster is required. New helper bones preserve
setup geometry; source weighted deforms are rotated into their new local basis.
"""
from copy import deepcopy
import math

from .joint_face_config import defaults, normalize, values, blink_value, sample_times
from .joint_face_inventory import inventory, weighted_points

PROFILE = 'source-art-facial-controls-v1'
MIN_EYE_SCALE = .08


def rotate(x, y, angle):
    c, s = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    return c*x-s*y, s*x+c*y


def _deforms(document, slot, attachment):
    for name, animation in document.get('animations', {}).items():
        if animation.get('deform', {}).get('default', {}).get(slot):
            raise ValueError('joint_face_legacy_deform_unsupported')
        for skin, slots in animation.get('attachments', {}).items():
            channels = slots.get(slot, {}).get(attachment, {})
            if channels.get('deform'):
                yield name, channels['deform']


def _reparent(document, part, anchor, angle):
    slot_name, attachment = part['slot'], part['attachment']
    mesh = document['skins'][0]['attachments'][slot_name][attachment]
    index = next(i for i, b in enumerate(document['bones']) if b['name'] == part['parent'])
    points = weighted_points(mesh, index)
    name = 'm5-face-' + slot_name
    if any(b['name'] == name for b in document['bones']):
        raise ValueError('joint_face_already_compiled')
    helper_index = len(document['bones'])
    document['bones'].append(dict(name=name, parent=part['parent'],
        x=anchor[0], y=anchor[1], rotation=angle, length=0))
    mesh['vertices'] = [v for x, y in points for v in
                        (1, helper_index, *rotate(x-anchor[0], y-anchor[1], -angle), 1.)]
    for _, keys in _deforms(document, slot_name, attachment):
        for key in keys:
            data = [0.] * (len(points)*2)
            offset = key.get('offset', 0)
            old = key.get('vertices', [])
            if not isinstance(offset, int) or offset < 0 or offset+len(old) > len(data):
                raise ValueError('joint_face_deform_size')
            data[offset:offset+len(old)] = old
            key['vertices'] = [v for i in range(0, len(data), 2)
                               for v in rotate(data[i], data[i+1], -angle)]
            key.pop('offset', None)
    for slot in document['slots']:
        if slot['name'] == slot_name:
            slot['bone'] = name
    return name


def _part_state(config, part, group, time):
    role = part['role']
    x = y = angle = 0.
    sx = sy = 1.
    turn = values(config['turn'], time, ('yaw', 'pitch'))
    # Small feature shifts only. The head/body source tracks are never edited.
    eye_width = group.get('white', part)['width']
    x += turn['yaw'] * min(5., eye_width*.12)
    y += turn['pitch'] * min(3., eye_width*.07)
    if role == 'iris' and group.get('gaze_available'):
        gaze = values(config['gaze'], time, ('x', 'y'))
        white = group['white']
        x += gaze['x'] * min(3., white['width']*.06)
        gaze_y = gaze['y'] * min(2., white['height']*.06)
        factor = 1-(1-MIN_EYE_SCALE)*blink_value(config, time) if group.get('blink_available') else 1
        y += gaze_y * factor
    if role in ('iris', 'white', 'lash') and group.get('blink_available'):
        sy = 1-(1-MIN_EYE_SCALE)*blink_value(config, time)
    if role == 'brow':
        brow = values(config['brows'], time, ('lift', 'tilt'))
        y += brow['lift'] * min(3., part['width']*.1)
        angle += brow['tilt'] * 5 * (-1 if part['side'] == 'r' else 1)
    if role == 'mouth':
        mouth = values(config['mouth'], time, ('open', 'wide'))
        sx = 1+mouth['wide']*.15
        sy = 1. if config['mouth']['template_enabled'] else 1+mouth['open']*.8
    return x, y, angle, sx, sy


def apply(files, document, animation, config, times):
    if animation not in document.get('animations', {}):
        raise ValueError('joint_face_animation_missing')
    config = normalize(config, max(times) if times else 0)
    report = dict(profile=PROFILE, enabled=config['enabled'], authority='none',
        status='disabled', affected_slots=[], affected_bones=[], sample_times=list(times),
        missing=[], limitations=[], channels={}, anchors={}, material_files_changed=[])
    if not config['enabled']:
        return document, {}, report
    source = inventory(files, document)
    parts = [p for p in source['parts'] if p['available']]
    if set(config['anchors']) - {p['slot'] for p in parts}:
        raise ValueError('joint_face_anchor_target_missing')
    report.update(inventory=source, missing=source['missing'], material_gaps=source['material_gaps'],
                  effect_kinds=source['effect_kinds'], limitations=source['limitations'],
                  status='sampled_candidate_requires_visual_review')
    if config['mouth']['template_enabled'] and not source['mouth_template_available']:
        report['missing'].append('mouth_template')
    grid = sample_times(config, times)
    result = deepcopy(document)
    updates = {}
    generated_templates = []
    target = result['animations'][animation]
    groups = {}
    for side in ('l', 'r', 'center'):
        groups[side] = {p['role']: p for p in parts if p['side'] == side}
        groups[side].update(source['eyes'].get(side, {}))
    for part in parts:
        group = groups[part['side']]
        eye = part['role'] in ('iris', 'white', 'lash')
        anchor_part = group['white'] if eye and group.get('blink_available') else part
        anchor = config['anchors'].get(part['slot'], config['anchors'].get(anchor_part['slot'], anchor_part['anchor']))
        angle = anchor_part['rotation']
        # Existing attachment switches require a full state mapping, not silent changes.
        if any(a.get('slots', {}).get(part['slot'], {}).get('attachment')
               for a in document['animations'].values()):
            raise ValueError('joint_face_attachment_timeline_requires_mapping')
        helper = _reparent(result, part, anchor, angle)
        track = dict(translate=[], rotate=[], scale=[])
        for time in grid:
            dx, dy, turn, sx, sy = _part_state(config, part, group, time)
            px, py = rotate(dx, dy, angle)
            track['translate'].append(dict(time=time, x=px, y=py))
            track['rotate'].append(dict(time=time, value=turn))
            track['scale'].append(dict(time=time, x=sx, y=sy))
        target.setdefault('bones', {})[helper] = track
        report['affected_slots'].append(part['slot'])
        report['affected_bones'].append(helper)
        report['anchors'][part['slot']] = list(anchor)
        report['channels'][part['slot']] = dict(role=part['role'], side=part['side'], helper=helper,
            min_scale_x=min(k['x'] for k in track['scale']),
            min_scale_y=min(k['y'] for k in track['scale']),
            max_scale_x=max(k['x'] for k in track['scale']),
            max_scale_y=max(k['y'] for k in track['scale']))
        if (part['role'] in ('iris', 'white') and group.get('blink_available')
                and config['blink']['enabled']):
            original = target.get('slots', {}).get(part['slot'], {})
            if set(original) & {'alpha', 'rgba', 'rgba2', 'color', 'twoColor'}:
                raise ValueError('joint_face_existing_alpha_requires_composition')
            slot = next(s for s in document['slots'] if s['name'] == part['slot'])
            setup_alpha = int(slot.get('color', 'ffffffff')[-2:], 16)/255
            target.setdefault('slots', {}).setdefault(part['slot'], {})['alpha'] = [
                dict(time=t, value=setup_alpha*max(0., 1-blink_value(config, t)/.8)) for t in grid]
        if (part['role'] == 'mouth' and part.get('template_available')
                and config['mouth']['enabled'] and config['mouth']['template_enabled']):
            from .joint_face_mouth import add_template
            changed, generated = add_template({**files, **updates}, result, animation, config, part, helper, grid)
            updates.update(changed); generated_templates.append(generated)
            report['affected_slots'].append(generated['slot'])
            report['affected_bones'].append(generated['helper'])
            report['channels'][generated['slot']] = {**generated, 'role': 'mouth_template', 'side': part['side']}
    report.update(sample_times=grid, enabled_effects=[name for name, available in source['capabilities'].items()
                  if available and config[name]['enabled']],
                  controls=config, inherited_body_tracks_unchanged=True,
                  old_facial_deforms='basis_converted_for_all_animations',
                  min_eye_scale=MIN_EYE_SCALE, generated_templates=generated_templates,
                  material_files_changed=sorted(updates))
    if generated_templates:
        custom = bool(config['mouth'].get('template_image'))
        report['effect_kinds']['mouth'] = ('user_provided' if custom else 'generated')+'_template_interior_with_source_mouth_crossfade'
        report['limitations'] += (['user_mouth_template_requires_character_visual_review'] if custom
            else ['mouth_template_is_generated_candidate_not_character_authored_variant'])
    report['limitations'] += ['gaze_is_conservative_bounded_offset_not_per_pixel_eye_socket_clipping',
                              'partial_blink_source_lash_shape_requires_visual_review',
                              'limited_feature_turn_not_geometry_or_occlusion_reconstruction']
    return result, updates, report
