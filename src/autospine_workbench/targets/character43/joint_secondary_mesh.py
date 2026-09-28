"""Root-pinned hair mesh and deformation-preserving clothing response helpers."""
from copy import deepcopy
import math

from ...asset.planning.skirt_mesh import build_skirt_mesh
from .affine_pose import matrices, sample
from .skirt_candidate import inverse
from .skirt_contact import source_image


def smooth(value):
    t = max(0., min(1., value))
    return t*t*(3-2*t)


def hair(files, document, slot, root_fraction, step=24):
    choices = document['skins'][0]['attachments'][slot]
    if set(choices) != {slot}:
        raise ValueError('joint_hair_attachment_variants')
    for animation in document['animations'].values():
        if animation.get('attachments', {}).get('default', {}).get(slot):
            raise ValueError('joint_hair_existing_deform')
        if animation.get('slots', {}).get(slot, {}).get('attachment'):
            raise ValueError('joint_hair_attachment_timeline')
    setup = dict(document, animations={'setup': {}})
    points = sample(setup, 'setup', 0)[0]
    image, origin = source_image(files, document, points, slot)
    alpha = image.getchannel('A'); bounds = alpha.getbbox()
    if not bounds: raise ValueError('joint_hair_empty')
    waist = bounds[1] + (bounds[3]-bounds[1])*root_fraction
    # Reuse the alpha-covering tessellator; neutral pelvis means the fixed head.
    pixels = list(alpha.tobytes())
    mesh = build_skirt_mesh([pixels[i:i+image.width] for i in range(0, len(pixels), image.width)], waist, step)
    to_world = lambda p: (origin[0]+p[0], origin[1]-p[1])
    names = {'pelvis': 'head'}; helpers = []
    for chain in mesh['helper_chains']:
        parent = 'head'
        for i, suffix in enumerate(('upper', 'lower')):
            name = 'm5-hair-'+slot+'-'+chain['id'].replace('skirt_', '')+'-'+suffix
            transform = matrices(dict(document, animations={'setup': {}}), 'setup', 0)[parent]
            start, end = [inverse(transform, to_world(p)) for p in chain['points'][i:i+2]]
            dx, dy = end[0]-start[0], end[1]-start[1]
            document['bones'].append(dict(name=name, parent=parent, x=start[0], y=start[1],
                rotation=math.degrees(math.atan2(dy, dx)), length=math.hypot(dx, dy)))
            names[chain['id']+'_'+suffix] = name; helpers.append(name); parent = name
    transforms = matrices(dict(document, animations={'setup': {}}), 'setup', 0)
    indices = {b['name']: i for i, b in enumerate(document['bones'])}; flat = []; pinned = []
    for i, (point, influences) in enumerate(zip(mesh['vertices'], mesh['influences'], strict=True)):
        flat.append(len(influences))
        for influence in influences:
            name = names[influence['bone']]; x, y = inverse(transforms[name], to_world(point))
            flat.extend([indices[name], x, y, influence['weight']])
        if point[1] <= waist: pinned.append(i)
    attachment = choices[slot]
    attachment.update(vertices=flat, uvs=[v for p in mesh['uvs'] for v in p],
                      triangles=[v for t in mesh['triangles'] for v in t])
    for key in ('edges', 'hull'): attachment.pop(key, None)
    return dict(slot=slot, helpers=helpers, pinned_vertices=pinned,
        expected_setup=[list(to_world(p)) for p in mesh['vertices']],
        root_fraction=root_fraction, root_local_y=waist, vertex_count=len(mesh['vertices']),
        region_kind='hair', root_driver='head', strategy='fixed-scalp-three-two-bone-alpha-mesh',
        root_policy='upper_source_alpha_band_candidate', source_rgba_preserved=True)


def _rows(attachment):
    data = attachment['vertices']; out = []; i = 0; old_offset = 0
    while i < len(data):
        count = data[i]; i += 1; row = []
        for _ in range(count):
            index, x, y, weight = data[i:i+4]; i += 4
            row.append((index, x, y, weight, old_offset)); old_offset += 2
        out.append(row)
    return out, old_offset


def cloth(document, slot, helper_names):
    """Split only movable helper influences; clone every old deform component.

    Identity child transforms make every old deformed pose EXACT at zero new
    response. Body-mixed boundary vertices and the initial root band stay fixed.
    """
    choices = document['skins'][0]['attachments'][slot]
    if set(choices) != {slot}: raise ValueError('joint_cloth_attachment_variants')
    attachment = choices[slot]; rows, old_size = _rows(attachment)
    bones = document['bones']; name_map = {b['name']: i for i, b in enumerate(bones)}
    selected = {name_map[name]: name for name in helper_names}; child_indices = {}
    for index, name in selected.items():
        child_indices[index] = len(bones)
        bones.append(dict(name='m5-response-'+name, parent=name, x=0., y=0., rotation=0.,
                          length=bones[index].get('length', 1.)))
    flat = []; clone_offsets = []; pinned = []; moved = 0
    for vi, row in enumerate(rows):
        mixed_body = any(index not in selected and weight > 1e-8 for index, _, _, weight, _ in row)
        expanded = []
        for index, x, y, weight, offset in row:
            length = max(8., bones[index].get('length', 1.))
            ratio = 0. if index not in selected or mixed_body else smooth((math.hypot(x, y)/length-.2)/.8)
            if ratio < 1-1e-9: expanded.append((index, x, y, weight*(1-ratio), offset))
            if ratio > 1e-9: expanded.append((child_indices[index], x, y, weight*ratio, offset))
        if all(index not in child_indices.values() for index, *_ in expanded): pinned.append(vi)
        else: moved += 1
        flat.append(len(expanded))
        for index, x, y, weight, offset in expanded:
            flat.extend([index, x, y, weight]); clone_offsets.extend([offset, offset+1])
    if not moved: raise ValueError('joint_cloth_no_free_vertices')
    attachment['vertices'] = flat
    for animation in document['animations'].values():
        keys = animation.get('attachments', {}).get('default', {}).get(slot, {}).get(slot, {}).get('deform', [])
        for key in keys:
            previous = [0.]*old_size; start = key.get('offset', 0); values = key.get('vertices', [])
            if start < 0 or start + len(values) > old_size: raise ValueError('joint_cloth_deform_size')
            previous[start:start+len(values)] = values
            key['vertices'] = [previous[i] for i in clone_offsets]; key.pop('offset', None)
    return dict(slot=slot, helpers=['m5-response-'+name for name in helper_names],
        pinned_vertices=pinned, movable_vertices=moved, region_kind='cloth',
        root_driver=[bones[i].get('parent') for i in selected],
        strategy='identity-child-response-fixed-root-body-boundary',
        existing_deform='component_clone_preserves_every_old_key_and_curve',
        helper_parents=helper_names)


def remove_probe(document, animation, helpers):
    """Only replace the exact legacy 17-key sinusoid, never arbitrary repairs."""
    removed = []
    tracks = document['animations'][animation].get('bones', {})
    for name in helpers:
        if '-skirt_' not in name: continue
        keys = tracks.get(name, {}).get('rotate', [])
        if len(keys) != 17 or any(set(k) != {'time', 'value'} for k in keys): continue
        end = keys[-1]['time']; amplitude = keys[4]['value']
        if end <= 0 or abs(abs(amplitude)-(1 if name.endswith('_lower') else 2)) > 1e-6 and abs(abs(amplitude)-(2 if name.endswith('_lower') else 4)) > 1e-6:
            continue
        if all(abs(k['time']-end*i/16) < 1e-7 and abs(k['value']-amplitude*math.sin(2*math.pi*i/16)) < 1e-7 for i, k in enumerate(keys)):
            del tracks[name]['rotate']; removed.append(name)
    return removed
