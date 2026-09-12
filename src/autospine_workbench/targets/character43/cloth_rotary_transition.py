"""Rotary interpolation of a wrist cloth/forearm pair, baked without changing weights."""
from copy import deepcopy
import math
from .affine_pose import matrices
from ..spine43.continuous_pose import interpolate


def point(matrix, x, y):
    a, b, c, d, tx, ty = matrix
    return (tx+a*x+b*y, ty+c*x+d*y)


def bake(document, name, helpers, samples=257):
    if type(samples) is not int or not 3 <= samples <= 1025:
        raise ValueError('cloth_rotary_sample_limit')
    result = deepcopy(document); animation = result['animations'][name]
    if animation.get('attachments'):
        raise ValueError('cloth_rotary_existing_deform')
    bones = {b['name']: b for b in document['bones']}
    if not helpers or len(set(helpers)) != len(helpers):
        raise ValueError('cloth_rotary_helper_inventory')
    for bone in bones.values():
        if bone.get('scaleX', 1) != 1 or bone.get('scaleY', 1) != 1:
            raise ValueError('cloth_rotary_scale_unsupported')
    tracks = animation['bones']
    if any(set(t)-{'rotate'} for t in tracks.values()):
        raise ValueError('cloth_rotary_channel_unsupported')
    if any(k.get('curve', 'linear') != 'linear' for t in tracks.values() for k in t.get('rotate', [])):
        raise ValueError('cloth_rotary_curve_unsupported')
    key_times = {k['time'] for t in tracks.values() for k in t.get('rotate', [])}
    duration = max(key_times)
    times = sorted(key_times | {duration*i/(samples-1) for i in range(samples)})
    setup = matrices(document, name, 0)
    transforms = [matrices(document, name, t) for t in times]

    def delta(bone, time):
        value = 0.; visited = set()
        while bone:
            if bone in visited: raise ValueError('cloth_rotary_cycle')
            visited.add(bone)
            if tracks.get(bone, {}).get('rotate'):
                value += interpolate(tracks[bone]['rotate'], time, 'value')
            bone = bones[bone].get('parent')
        return value

    rows = []
    for helper in sorted(helpers):
        if helper not in bones:
            raise ValueError('cloth_rotary_helper_invalid')
        slot = helper.removeprefix('cloth-'); parent = bones[helper].get('parent')
        if not helper.startswith('cloth-') or parent not in ('forearm_l', 'forearm_r'):
            raise ValueError('cloth_rotary_helper_invalid')
        attachment = document['skins'][0]['attachments'][slot][slot]
        data = attachment['vertices']; vertices = []; cursor = 0
        while cursor < len(data):
            count = data[cursor]; cursor += 1; entries = []
            for _ in range(count):
                index, x, y, weight = data[cursor:cursor+4]; cursor += 4
                entries.append((document['bones'][index]['name'], x, y, weight))
            if abs(sum(e[3] for e in entries)-1) > 1e-7:
                raise ValueError('cloth_rotary_weight_sum')
            vertices.append(entries)
        keys = []; maximum = 0.; affected = set()
        for time, current in zip(times, transforms):
            offsets = []; pivot = current[helper][4:]; rest_pivot = setup[helper][4:]
            if math.dist(pivot, point(current[parent], bones[helper]['x'], bones[helper]['y'])) > 1e-6:
                raise ValueError('cloth_rotary_anchor_mismatch')
            for index, entries in enumerate(vertices):
                pair = [e for e in entries if e[0] in (parent, helper) and e[3] > 0]
                cloth = sum(e[3] for e in pair if e[0] == helper)
                total = sum(e[3] for e in pair); dx = dy = 0.
                if cloth > 0 and total > cloth:
                    rest = point(setup[pair[0][0]], *pair[0][1:3])
                    if any(math.dist(rest, point(setup[e[0]], *e[1:3])) > 1e-5 for e in pair):
                        raise ValueError('cloth_rotary_setup_mismatch')
                    angle = math.radians(delta(parent, time)+(delta(helper, time)-delta(parent, time))*cloth/total)
                    x, y = rest[0]-rest_pivot[0], rest[1]-rest_pivot[1]
                    target = (pivot[0]+math.cos(angle)*x-math.sin(angle)*y,
                              pivot[1]+math.sin(angle)*x+math.cos(angle)*y)
                    dx, dy = [total*target[k]-sum(e[3]*point(current[e[0]], *e[1:3])[k] for e in pair) for k in (0, 1)]
                    affected.add(index); maximum = max(maximum, math.hypot(dx, dy))
                for bone, _, _, _ in entries:
                    a, b, c, d, _, _ = current[bone]; det = a*d-b*c
                    offsets.extend(((d*dx-b*dy)/det, (a*dy-c*dx)/det))
            keys.append(dict(time=time, vertices=offsets))
        animation.setdefault('attachments', {}).setdefault('default', {})[slot] = {slot: {'deform': keys}}
        rows.append(dict(slot=slot, affected_vertices=sorted(affected), max_lbs_difference_px=maximum,
                         sample_count=len(times)))
    return result, dict(profile='wrist-pair-rotary-interpolation-v1', authority='none', status='candidate',
                        records=rows, geometry_status='requires_independent_check',
                        limitation='nonlinear_skinning_not_bounded_area_repair')
