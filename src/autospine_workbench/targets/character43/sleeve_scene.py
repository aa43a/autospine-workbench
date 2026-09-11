"""Compose exact sleeve timelines into a character scene without changing their motion."""
from copy import deepcopy
import math

from ...resolved_project import canonical_sha256
from ..spine43.workbench_preview import rigid_quad


def _index(rows, field):
    result = {r[field]: r for r in rows}
    if len(result) != len(rows):
        raise ValueError('character_duplicate_identity')
    return result


def _remap(attachment, old, new):
    result = deepcopy(attachment)
    if result.get('type') != 'mesh':
        raise ValueError('character_unsupported_attachment')
    vertices = result['vertices']; cursor = 0
    for _ in range(len(result['uvs']) // 2):
        count = vertices[cursor]
        if type(count) is not int or not 1 <= count <= 4:
            raise ValueError('character_weight_encoding')
        total = 0
        for offset in range(count):
            pos = cursor + 1 + 4 * offset
            index = vertices[pos]
            if type(index) is not int or not 0 <= index < len(old):
                raise ValueError('character_bone_index')
            if not all(math.isfinite(v) for v in vertices[pos+1:pos+4]):
                raise ValueError('character_nonfinite_weight')
            if not 0 <= vertices[pos+3] <= 1:
                raise ValueError('character_weight_range')
            total += vertices[pos+3]
            vertices[pos] = new[old[index]['name']]
        if abs(total - 1) > 1e-7:
            raise ValueError('character_weight_sum')
        cursor += 1 + 4 * count
    if cursor != len(vertices):
        raise ValueError('character_weight_encoding')
    return result


def _residual_attachment(source, skeleton, indices):
    root = next(b for b in skeleton['bones'] if b['id'] == 'root')
    mesh = rigid_quad(source, root)
    vertices = []
    for entries in mesh['weights']:
        entry = entries[0]; x, y = entry['local_xy']
        vertices.extend([1, indices['root'], x, -y, 1])
    x, y, r, b = source['bbox']
    return dict(type='mesh', path=source['layer_id'], width=r-x, height=b-y,
                vertices=vertices, uvs=[0, 0, 1, 0, 1, 1, 0, 1], triangles=[0, 1, 2, 0, 2, 3])


def compose_scene(base, replacements, candidate, skeleton):
    """Replacements include all isolated components for a source and an explicit residual name.

    All participating sleeve tracks must agree by name. Existing body clips are not
    carried over: their rotations have not been validated with these corrective keys.
    """
    result = deepcopy(base)
    if base['skeleton']['spine'] != '4.3.26' or base.get('constraints'):
        raise ValueError('character_target_unsupported')
    sources = _index(candidate['layers'], 'layer_id')
    changes = _index(replacements, 'source_layer_id')
    base_slots = _index(base['slots'], 'name')
    bones = _index(result['bones'], 'name')
    documents = [doc for replacement in replacements for doc in replacement['documents']]
    if not documents:
        raise ValueError('character_no_replacements')
    tracks = set(documents[0]['animations'])
    if not tracks or any(set(doc['animations']) != tracks for doc in documents):
        raise ValueError('character_motion_inventory_mismatch')
    for doc in documents:
        if doc['skeleton']['spine'] != '4.3.26' or doc.get('constraints') \
                or any(doc['skeleton'][k] != base['skeleton'][k] for k in ('x', 'y', 'width', 'height')):
            raise ValueError('character_coordinate_mismatch')
        for bone in doc['bones']:
            if bone['name'] in bones and bone != bones[bone['name']]:
                raise ValueError('character_bone_setup_mismatch')
            if bone['name'] not in bones:
                if bone.get('parent') not in bones:
                    raise ValueError('character_helper_parent_missing')
                bones[bone['name']] = deepcopy(bone); result['bones'].append(deepcopy(bone))
    indices = {b['name']: i for i, b in enumerate(result['bones'])}
    attachments = result['skins'][0]['attachments']
    animations = {name: dict(bones={}, attachments={'default': {}}) for name in sorted(tracks)}
    owners = {}; installed = {}
    for source_id, replacement in changes.items():
        if source_id not in sources or source_id not in base_slots:
            raise ValueError('character_source_not_directly_represented')
        attachments.pop(source_id)
        slots = []
        for doc in replacement['documents']:
            if len(doc['skins']) != 1 or doc['skins'][0]['name'] != 'default':
                raise ValueError('character_skin_unsupported')
            for slot in doc['slots']:
                name = slot['name']
                if name in attachments or name in base_slots:
                    raise ValueError('character_duplicate_region')
                variants = doc['skins'][0]['attachments'][name]
                if set(variants) != {slot['attachment']}:
                    raise ValueError('character_attachment_inventory')
                attachments[name] = {key: _remap(value, doc['bones'], indices) for key, value in variants.items()}
                owners[name] = source_id; slots.append(deepcopy(slot))
            for track, animation in doc['animations'].items():
                if set(animation) - {'bones', 'attachments'}:
                    raise ValueError('character_animation_channel_unsupported')
                for bone, channels in animation.get('bones', {}).items():
                    previous = animations[track]['bones'].get(bone)
                    if previous is not None and previous != channels:
                        raise ValueError('character_motion_conflict')
                    animations[track]['bones'][bone] = deepcopy(channels)
                skins = animation.get('attachments', {})
                if set(skins) - {'default'}:
                    raise ValueError('character_deform_skin_unsupported')
                target = animations[track]['attachments']['default']
                for slot, timeline in skins.get('default', {}).items():
                    if slot in target or slot not in {s['name'] for s in doc['slots']}:
                        raise ValueError('character_deform_inventory')
                    target[slot] = deepcopy(timeline)
        residual = replacement.get('residual_id')
        if residual:
            if residual in attachments or residual in base_slots:
                raise ValueError('character_duplicate_region')
            attachment = _residual_attachment(sources[source_id], skeleton, indices)
            attachment['path'] = residual
            attachments[residual] = {residual: attachment}
            slots.append(dict(name=residual, bone='root', attachment=residual)); owners[residual] = source_id
        installed[source_id] = slots
    result['slots'] = [part for slot in base['slots'] for part in installed.get(slot['name'], [deepcopy(slot)])]
    result['animations'] = animations
    result['skeleton']['hash'] = canonical_sha256({'base': base, 'replacements': replacements})
    return result, owners
