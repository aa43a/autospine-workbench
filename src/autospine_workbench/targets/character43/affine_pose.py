"""Normal-inheritance Spine affine FK including animated axial scale."""
import math
from ..spine43.continuous_pose import interpolate


def _pair(keys, time, default=None):
    """Read two channels without rebuilding every key into a temporary vector."""
    i = 0
    while i+1 < len(keys) and keys[i+1]['time'] <= time:
        i += 1
    a, b = keys[i], keys[min(i+1, len(keys)-1)]
    f = 0 if a.get('curve') == 'stepped' or a['time'] == b['time'] else (time-a['time'])/(b['time']-a['time'])
    values = []
    for key in ('x', 'y'):
        x, y = (a[key], b[key]) if default is None else (a.get(key, default), b.get(key, default))
        values.append(x+f*(y-x))
    return values


def matrices(document, animation_name, time):
    animation = document['animations'][animation_name]
    transforms = {}
    for bone in document['bones']:
        if bone.get('inherit', 'normal') != 'normal' or bone.get('shearX', 0) or bone.get('shearY', 0):
            raise ValueError('character_affine_transform_unsupported')
        tracks = animation.get('bones', {}).get(bone['name'], {})
        rotation = bone['rotation']
        if tracks.get('rotate'):
            rotation += interpolate(tracks['rotate'], time, 'value')
        x, y = bone['x'], bone['y']
        sx, sy = bone.get('scaleX', 1), bone.get('scaleY', 1)
        for kind in ('translate', 'scale'):
            keys = tracks.get(kind)
            if keys:
                u, v = _pair(keys, time)
                if kind == 'translate':
                    x += u; y += v
                else:
                    sx *= u; sy *= v
        if not all(math.isfinite(v) for v in (rotation, x, y, sx, sy)) or sx <= 0 or sy <= 0:
            raise ValueError('character_affine_nonpositive_scale')
        shear_x = shear_y = 0.
        if tracks.get('shear'):
            shear_x,shear_y=_pair(tracks['shear'],time,0)
            if not all(math.isfinite(v) for v in (shear_x,shear_y)):
                raise ValueError('character_affine_shear_nonfinite')
        angle = math.radians(rotation+shear_x)
        if tracks.get('shear'):
            other=math.radians(rotation+90+shear_y)
            a,b,c,d=math.cos(angle)*sx,math.cos(other)*sy,math.sin(angle)*sx,math.sin(other)*sy
            if a*d-b*c<=1e-10:raise ValueError('character_affine_shear_singular')
        else:
            a, b = math.cos(angle)*sx, -math.sin(angle)*sy
            c, d = math.sin(angle)*sx, math.cos(angle)*sy
        parent = bone.get('parent')
        if parent:
            if parent not in transforms:
                raise ValueError('character_affine_parent_order')
            pa, pb, pc, pd, px, py = transforms[parent]
            a, b, c, d, x, y = (pa*a+pb*c, pa*b+pb*d, pc*a+pd*c, pc*b+pd*d,
                                px+pa*x+pb*y, py+pc*x+pd*y)
        transforms[bone['name']] = (a, b, c, d, x, y)
    return transforms


def sample(document, animation_name, time):
    return sample_with_matrices(document, animation_name, time)[:2]


def sample_with_matrices(document, animation_name, time):
    """Expose the FK already computed for this exact sample to its caller."""
    if any(channels.get('attachment') for channels in
           document['animations'][animation_name].get('slots', {}).values()):
        raise ValueError('character_affine_attachment_timeline_requires_active_mesh_sampler')
    transforms = matrices(document, animation_name, time)
    animation = document['animations'][animation_name]
    result = {}
    for slot, choices in document['skins'][0]['attachments'].items():
        attachment = choices[slot]
        data = attachment['vertices']
        keys = animation.get('attachments', {}).get('default', {}).get(slot, {}).get(slot, {}).get('deform')
        offsets = interpolate(keys, time, 'vertices') if keys else []
        i = j = 0; points = []
        while i < len(data):
            count = data[i]; i += 1; x = y = 0.
            for _ in range(count):
                index, lx, ly, weight = data[i:i+4]; i += 4
                if offsets:
                    lx += offsets[j]; ly += offsets[j+1]
                j += 2
                a, b, c, d, tx, ty = transforms[document['bones'][index]['name']]
                x += weight*(tx+a*lx+b*ly)
                y += weight*(ty+c*lx+d*ly)
            points.append([x, y])
        result[slot] = points
    pose = {name: (m[4], m[5], math.degrees(math.atan2(m[2], m[0]))) for name, m in transforms.items()}
    return result, pose, transforms
