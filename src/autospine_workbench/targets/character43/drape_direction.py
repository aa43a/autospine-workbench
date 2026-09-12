"""Setup-world direction hold for explicitly selected wrist-rooted cloth helpers."""
from copy import deepcopy
import math
from ..spine43.continuous_pose import interpolate


def apply(document, animation_name, helpers):
    bones = {b['name']: b for b in document['bones']}
    if not helpers or len(set(helpers)) != len(helpers) or len(bones) != len(document['bones']):
        raise ValueError('drape_direction_inventory')
    result = deepcopy(document)
    tracks = result['animations'][animation_name].setdefault('bones', {})
    rows = []
    for name in sorted(helpers):
        bone = bones.get(name)
        if not name.startswith('cloth-') or name[6:] not in document['skins'][0]['attachments']:
            raise ValueError('drape_direction_helper_identity')
        if not bone or bone.get('parent') not in ('forearm_l', 'forearm_r'):
            raise ValueError('drape_direction_helper_parent')
        hand = bones.get('hand_'+bone['parent'][-1])
        if not hand or hand.get('parent') != bone['parent'] or math.dist(
                (bone['x'], bone['y']), (hand['x'], hand['y'])) > 1e-6:
            raise ValueError('drape_direction_helper_anchor')
        if name in tracks or any(b.get('parent') == name for b in bones.values()):
            raise ValueError('drape_direction_existing_driver')
        ancestors = []; current = bone['parent']
        while current:
            if current in ancestors or current not in bones:
                raise ValueError('drape_direction_topology')
            ancestors.append(current); current = bones[current].get('parent')
        for target in [name, *ancestors]:
            b = bones[target]
            if b.get('inherit', 'normal') != 'normal' or any(b.get(k, 0) for k in ('shearX', 'shearY')) \
                    or b.get('scaleX', 1) != 1 or b.get('scaleY', 1) != 1:
                raise ValueError('drape_direction_transform_unsupported')
            for channel, keys in tracks.get(target, {}).items():
                if channel != 'rotate' or any(k.get('curve', 'linear') != 'linear' for k in keys):
                    raise ValueError('drape_direction_channel_unsupported')
        times = sorted({0.} | {k['time'] for target in ancestors
                               for k in tracks.get(target, {}).get('rotate', [])})
        keys = [dict(time=t, value=-sum(interpolate(tracks[a]['rotate'], t, 'value')
                    for a in ancestors if tracks.get(a, {}).get('rotate'))) for t in times]
        if any(not math.isfinite(k['value']) for k in keys):
            raise ValueError('drape_direction_nonfinite')
        if abs(keys[0]['value']) > 1e-7:
            raise ValueError('drape_direction_setup_changed')
        tracks[name] = {'rotate': keys}
        rows.append(dict(bone=name, parent=bone['parent'], key_count=len(keys),
                         maximum_compensation_degrees=max(abs(k['value']) for k in keys)))
    return result, dict(profile='wrist-cloth-setup-world-direction-v1', authority='none',
                        status='candidate', records=rows, contact_status='not_evaluated',
                        limitation='direction_hold_not_gravity_simulation')
