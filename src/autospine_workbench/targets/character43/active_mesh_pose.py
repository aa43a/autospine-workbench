"""Sample the active mesh identity, topology and matching deform per slot.

Explicit opt-in for attachment variants. The ordinary fixed-topology evaluator
must not silently substitute a setup mesh for a switched pose attachment.
"""
from copy import deepcopy
import math
import struct

from .affine_pose import sample
from .deform_addition import entries, value


def active_document(document, animation, time):
    if type(time) not in (int, float) or not math.isfinite(time) or time < 0:
        raise ValueError('active_mesh_time_invalid')
    if len(document['skins']) != 1 or document['skins'][0].get('name', 'default') != 'default':
        raise ValueError('active_mesh_default_skin_required')
    motion = document['animations'][animation]
    if motion.get('deform'):
        raise ValueError('active_mesh_legacy_deform_unsupported')
    # Dense deform tracks can dominate the document. They are replaced below
    # with one sampled key, so copying all of them per frame is wasted work.
    normalized = deepcopy({k:v for k,v in document.items() if k not in ('animations','skins')})
    normalized['skins'] = [deepcopy({k:v for k,v in document['skins'][0].items() if k != 'attachments'})]
    normalized['animations'] = {k:deepcopy(v) for k,v in document['animations'].items() if k != animation}
    target = normalized['animations'][animation] = deepcopy({k:v for k,v in motion.items() if k not in ('slots','attachments')})
    target['attachments'] = {'default': {}}
    target_meshes = normalized['skins'][0]['attachments'] = {}
    identities = {}
    for slot in document['slots']:
        slot_name = slot['name']
        name = slot.get('attachment')
        previous = -1.
        for key in motion.get('slots', {}).get(slot_name, {}).get('attachment', []):
            timestamp = key.get('time', 0)
            if type(timestamp) not in (int, float) or not math.isfinite(timestamp) or timestamp < 0:
                raise ValueError('active_mesh_key_time_invalid')
            effective = struct.unpack('f', struct.pack('f', timestamp))[0]
            if not math.isfinite(effective) or effective <= previous:
                raise ValueError('active_mesh_key_order_or_float32_collision')
            previous = effective
            if time >= effective:
                name = key.get('name')
        identities[slot_name] = name
        if name is None:
            continue
        choices = document['skins'][0]['attachments'].get(slot_name, {})
        if name not in choices:
            raise ValueError('active_mesh_attachment_missing')
        mesh = choices[name]
        if mesh.get('type') != 'mesh' or mesh.get('parent'):
            raise ValueError('active_mesh_weighted_mesh_required')
        influences = entries(mesh)
        if len(influences)*2 != len(mesh['uvs']):
            raise ValueError('active_mesh_vertex_count_mismatch')
        target_meshes[slot_name] = {slot_name: deepcopy(mesh)}
        keys = motion.get('attachments', {}).get('default', {}).get(slot_name, {}).get(name, {}).get('deform', [])
        if keys:
            effective_keys = []
            previous = -1.
            for key in keys:
                timestamp = key.get('time', 0)
                if type(timestamp) not in (int, float) or not math.isfinite(timestamp) or timestamp < 0:
                    raise ValueError('active_mesh_deform_time_invalid')
                effective = struct.unpack('f', struct.pack('f', timestamp))[0]
                if not math.isfinite(effective) or effective <= previous:
                    raise ValueError('active_mesh_deform_key_order_or_float32_collision')
                previous = effective
                effective_keys.append({**key, 'time': effective})
            size = 2*sum(len(row) for row in influences)
            # Before the first key Runtime keeps setup deform, not the first value.
            offsets = [0.]*size if time < effective_keys[0]['time'] else value(effective_keys, time, size)
            target['attachments']['default'][slot_name] = {slot_name: {
                'deform': [dict(time=0, vertices=offsets)]}}
    return normalized, identities


def sample_active(document, animation, time):
    normalized, identities = active_document(document, animation, time)
    points, bones = sample(normalized, animation, time)
    setup = dict(normalized, animations={'setup': {}})
    rest = sample(setup, 'setup', 0)[0]
    meshes = normalized['skins'][0]['attachments']
    return dict(attachments=identities, vertices=points, bones=bones, setup_vertices=rest,
                triangles={slot: choices[slot]['triangles'] for slot, choices in meshes.items()})
