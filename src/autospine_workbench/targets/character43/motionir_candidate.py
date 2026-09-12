"""Setup-local MotionIR candidate on an existing canonical rig; no adoption."""
from copy import deepcopy
import math

from ...motion_validation import require_motion_ir, motion_ir_sha256
from ..spine43.continuous_pose import interpolate, world
from .wave_motion import pose

ROLES = {'humanoid.root': 'root', 'humanoid.spine.lower': 'spine',
         'humanoid.spine.upper': 'chest', 'humanoid.neck': 'neck', 'humanoid.head': 'head'}
for side, suffix in [('left', 'l'), ('right', 'r')]:
    for role, name in [('arm.upper', 'upperarm'), ('arm.lower', 'forearm'),
                       ('leg.upper', 'thigh'), ('leg.lower', 'calf'), ('clavicle', 'clavicle')]:
        ROLES['humanoid.'+role+'.'+side] = name+'_'+suffix


def build(document, motion, name):
    require_motion_ir(motion)
    if not name or name in document['animations']:
        raise ValueError('character_motion_name_conflict')
    bones = {b['name']: b for b in document['bones']}
    if len(bones) != len(document['bones']) or bones.get('root', {}).get('parent'):
        raise ValueError('character_motion_root_invalid')
    for side in ('l', 'r'):
        for child, parent in [('calf', 'thigh'), ('foot', 'calf'), ('forearm', 'upperarm'), ('hand', 'forearm')]:
            if bones.get(child+'_'+side, {}).get('parent') != parent+'_'+side:
                raise ValueError('character_motion_topology_invalid')
    length = sum(math.hypot(bones[n]['x'], bones[n]['y'])
                 for n in ('calf_l', 'foot_l', 'calf_r', 'foot_r'))/2
    if not math.isfinite(length) or length <= 0:
        raise ValueError('character_motion_reference_invalid')
    animation = {'bones': {}}
    for track in motion['tracks']:
        target = ROLES.get(track['target'])
        rotation = track['property'] == 'rotation'
        if track['target_kind'] != 'bone_role' or target not in bones or (
                not rotation and (target != 'root' or track['property'] != 'translation')):
            raise ValueError('character_motion_track_unsupported')
        if track['interpolation'] != 'linear':
            raise ValueError('character_motion_interpolation_unsupported')
        keys = []
        for key in track['keys']:
            row = dict(time=key['tick']/motion['ticks_per_second'])
            if rotation:
                row['value'] = -key['value']
            else:
                row.update(x=key['value'][0]*length, y=-key['value'][1]*length)
            keys.append(row)
        animation['bones'].setdefault(target, {})['rotate' if rotation else 'translate'] = keys
    result = deepcopy(document)
    result['animations'][name] = animation
    return result, dict(profile='canonical-motionir-setup-delta-v1', authority='none',
                        motion_sha256=motion_ir_sha256(motion), reference_length_px=length,
                        contact_mode='annotation_only', status='preview_only',
                        projection_suitability='unverified',
                        limitation='projected_source_pose_is_not_target_pose_fit')


def sample(document, name, time):
    """Evaluate translation separately because the existing mesh FK handles rotation."""
    if any(t.get('scale') for t in document['animations'][name].get('bones', {}).values()):
        from .affine_pose import sample as affine_sample
        return affine_sample(document, name, time)
    isolated = deepcopy(document)
    animation = isolated['animations'][name]
    isolated['animations'] = {name: animation}
    rotations = {}
    for bone in isolated['bones']:
        tracks = animation['bones'].get(bone['name'], {})
        if tracks.get('translate'):
            keys = [dict(time=k['time'], vertices=[k['x'], k['y']]) for k in tracks['translate']]
            dx, dy = interpolate(keys, time, 'vertices')
            bone['x'] += dx
            bone['y'] += dy
        if tracks.get('rotate'):
            rotations[bone['name']] = interpolate(tracks['rotate'], time, 'value')
    return world(isolated, time), pose(isolated['bones'], rotations)
