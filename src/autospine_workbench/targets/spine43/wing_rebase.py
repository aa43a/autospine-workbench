"""Re-express diagnostic wing influences in a canonical setup frame."""
from copy import deepcopy
import math
from .continuous_pose import world


def local(x, y, frame):
    px, py, angle = frame
    a = math.radians(-angle)
    return [(x-px)*math.cos(a)-(y-py)*math.sin(a), (x-px)*math.sin(a)+(y-py)*math.cos(a)]


def setup_frames(bones):
    frames = {}
    for bone in bones:
        parent = bone.get('parent')
        if bone['name'] in frames or (parent is not None and parent not in frames):
            raise ValueError('wing_rebase_topology')
        x, y, angle = frames[parent] if parent else (0, 0, 0)
        a = math.radians(angle)
        frames[bone['name']] = (x+bone['x']*math.cos(a)-bone['y']*math.sin(a),
                               y+bone['x']*math.sin(a)+bone['y']*math.cos(a), angle+bone['rotation'])
    return frames


def rebase(source, canonical):
    if len(source['animations']) != 1 or len(canonical['animations']) != 1:
        raise ValueError('wing_rebase_animation_inventory')
    for doc in (source, canonical):
        if doc['skeleton']['spine'] != '4.3.26':
            raise ValueError('wing_rebase_version')
        if any(doc.get(k) for k in ('ik', 'transform', 'path', 'physics')):
            raise ValueError('wing_rebase_constraints_unsupported')
        clip = next(iter(doc['animations'].values()))
        if any(set(track) != {'rotate'} for track in clip['bones'].values()):
            raise ValueError('wing_rebase_tracks_unsupported')
        for b in doc['bones']:
            if any(k in b for k in ('scaleX', 'scaleY', 'shearX', 'shearY', 'inherit')):
                raise ValueError('wing_rebase_transform_unsupported')
    old_frames = setup_frames(source['bones'])
    new_bones = deepcopy(canonical['bones'])
    frames = setup_frames(new_bones)
    if 'chest' not in frames or set(old_frames).intersection(frames) != {'root', 'chest'}:
        raise ValueError('wing_rebase_bone_collision')
    old_clip = next(iter(source['animations'].values()))
    if set(old_clip) != {'bones'} or 'root' in old_clip['bones']:
        raise ValueError('wing_rebase_source_tracks')
    for bone in source['bones']:
        if bone['name'] in ('root', 'chest'):
            continue
        parent = bone['parent']
        x, y, angle = old_frames[bone['name']]
        px, py = local(x, y, frames[parent])
        new_bones.append(dict(name=bone['name'], parent=parent, x=px, y=py, rotation=angle-frames[parent][2]))
        frames = setup_frames(new_bones)
    indices = {b['name']: i for i, b in enumerate(new_bones)}
    result = deepcopy(source)
    result['bones'] = new_bones
    for entries in result['skins'][0]['attachments'].values():
        for attachment in entries.values():
            if attachment['type'] != 'mesh':
                raise ValueError('wing_rebase_weighted_mesh_required')
            data = attachment['vertices']; i = 0
            while i < len(data):
                count = data[i]; i += 1
                if type(count) is not int or count < 1:
                    raise ValueError('wing_rebase_influences')
                for _ in range(count):
                    index, lx, ly, weight = data[i:i+4]
                    if type(index) is not int or not 0 <= index < len(source['bones']):
                        raise ValueError('wing_rebase_influence_index')
                    name = source['bones'][index]['name']
                    x, y, angle = old_frames[name]; a = math.radians(angle)
                    wx, wy = x+lx*math.cos(a)-ly*math.sin(a), y+lx*math.sin(a)+ly*math.cos(a)
                    data[i:i+4] = [indices[name], *local(wx, wy, frames[name]), weight]; i += 4
    tracks = deepcopy(old_clip['bones']); tracks.pop('chest', None)
    result['animations'] = {'wing-canonical-inspection': {'bones': tracks}}
    reference = deepcopy(source)
    next(iter(reference['animations'].values()))['bones'].pop('chest', None)
    error = 0
    for tick in range(121):
        before, after = world(reference, tick/60), world(result, tick/60)
        error = max(error, *(math.dist(p, q) for n in before for p, q in zip(before[n], after[n])))
    if error > 1e-7:
        raise ValueError('wing_rebase_motion_changed')
    return result, error
