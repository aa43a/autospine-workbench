"""Independent Spine 4.3 typed-array input model; ideal QA remains separate."""
from copy import deepcopy
from hashlib import sha256
import json
import math
from pathlib import Path
import struct

from .motionir_candidate import sample
from .numeric_reference import read

PROFILE = 'spine43-linear-weighted-float32-storage-v1'


def f32(value):
    result = struct.unpack('<f', struct.pack('<f', value))[0]
    if not math.isfinite(result):
        raise ValueError('runtime_storage_nonfinite')
    return result


def require_distinct_times(keys):
    if any(b['time'] <= a['time'] for a, b in zip(keys, keys[1:])):
        raise ValueError('runtime_storage_key_times_collapsed')


def stored_document(document):
    """Model only arrays used by the supported official JSON parser/timelines.

    Bone setup fields remain JS numbers. Weighted attachment coordinates/weights,
    timeline frames and deform key arrays are Float32Array in spine-core 4.3.13.
    This copy is evaluated independently, never exported as the user's rig.
    """
    result = deepcopy(document)
    for skin in result['skins']:
        for slot in skin['attachments'].values():
            for attachment in slot.values():
                if attachment.get('type') != 'mesh':
                    raise ValueError('runtime_storage_attachment_unsupported')
                data = attachment['vertices']
                if len(data) == len(attachment['uvs']):
                    raise ValueError('runtime_storage_unweighted_unsupported')
                i = 0
                while i < len(data):
                    count = data[i]
                    if type(count) is not int or count < 1:
                        raise ValueError('runtime_storage_weights_invalid')
                    i += 1
                    for _ in range(count):
                        for offset in (1, 2, 3):
                            data[i+offset] = f32(data[i+offset])
                        i += 4
    for animation in result['animations'].values():
        if set(animation) - {'bones', 'attachments', 'drawOrder'}:
            raise ValueError('runtime_storage_animation_unsupported')
        for key in animation.get('drawOrder', []):
            if set(key)-{'time', 'offsets'}:
                raise ValueError('runtime_storage_draw_order_unsupported')
            key['time'] = f32(key.get('time', 0))
        require_distinct_times(animation.get('drawOrder', []))
        for tracks in animation.get('bones', {}).values():
            for prop, keys in tracks.items():
                if prop not in ('rotate', 'translate', 'scale', 'shear'):
                    raise ValueError('runtime_storage_track_unsupported')
                for key in keys:
                    if 'curve' in key:
                        raise ValueError('runtime_storage_curve_unsupported')
                    for field in ('time', 'value', 'x', 'y'):
                        if field in key:
                            key[field] = f32(key[field])
                require_distinct_times(keys)
        for skin in animation.get('attachments', {}).values():
            for slot in skin.values():
                for tracks in slot.values():
                    if set(tracks) - {'deform'}:
                        raise ValueError('runtime_storage_attachment_track_unsupported')
                    for key in tracks.get('deform', []):
                        if 'curve' in key or key.get('offset', 0):
                            raise ValueError('runtime_storage_deform_unsupported')
                        key['time'] = f32(key['time'])
                        key['vertices'] = [f32(v) for v in key['vertices']]
                    require_distinct_times(tracks.get('deform', []))
    return result


def build(files):
    ideal = read(files)
    digest = sha256(files['skeleton.json']).hexdigest()
    if ideal['skeleton_sha256'] != digest:
        raise ValueError('runtime_storage_source_mismatch')
    document = stored_document(json.loads(files['skeleton.json']))
    frames = {}
    maximum = 0.
    for name, rows in ideal['animations'].items():
        frames[name] = []
        for row in rows:
            points = sample(document, name, row['time'])[0]
            if set(points) != set(row['vertices']):
                raise ValueError('runtime_storage_slot_inventory')
            for slot, values in points.items():
                if len(values) != len(row['vertices'][slot]):
                    raise ValueError('runtime_storage_vertex_inventory')
                maximum = max(maximum, *(math.dist(a, b) for a, b in zip(values, row['vertices'][slot])))
            frames[name].append(dict(time=row['time'], vertices=points))
    return dict(schema='autospine.runtime-storage-reference/v1', profile=PROFILE,
        skeleton_sha256=digest, runtime_version='4.3.13', animations=frames,
        implementation_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
        max_storage_displacement_px=maximum, ideal_geometry_reference_preserved=True,
        authority='none')
