"""Render labels from complete limb influence sets, never majority-weight guesses."""
from collections import Counter
import math


def classify(document, mesh, side):
    if side not in ('l', 'r'):
        raise ValueError('limb_region_side')
    names = [b['name'] for b in document['bones']]
    allowed = {part+'_'+side: part for part in ('upperarm', 'forearm', 'hand')}
    if not set(allowed) <= set(names) or len(names) != len(set(names)):
        raise ValueError('limb_region_bones')
    data = mesh.get('vertices', [])
    if mesh.get('type') != 'mesh' or len(data) == len(mesh.get('uvs', [])):
        raise ValueError('limb_region_weighted_required')
    vertices = []; cursor = 0
    while cursor < len(data):
        count = data[cursor]; cursor += 1
        if type(count) is not int or count < 1 or cursor+4*count > len(data):
            raise ValueError('limb_region_weights')
        influences = set(); total = 0
        for _ in range(count):
            index, x, y, weight = data[cursor:cursor+4]; cursor += 4
            if (type(index) is not int or not 0 <= index < len(names)
                    or any(not isinstance(v, (int, float)) or not math.isfinite(v) for v in (x,y,weight))
                    or weight < 0):
                raise ValueError('limb_region_weights')
            total += weight
            if weight > 0: influences.add(names[index])
        if not math.isclose(total, 1, abs_tol=1e-5):
            raise ValueError('limb_region_weight_sum')
        vertices.append(influences)
    flat = mesh.get('triangles', [])
    if (len(vertices)*2 != len(mesh.get('uvs', [])) or not flat or len(flat)%3
            or any(type(i) is not int or not 0 <= i < len(vertices) for i in flat)):
        raise ValueError('limb_region_inventory')
    labels = []
    for offset in range(0, len(flat), 3):
        influences = set().union(*(vertices[i] for i in flat[offset:offset+3]))
        if not influences <= set(allowed):
            label = 'unmapped'
        elif len(influences) == 1:
            label = allowed[next(iter(influences))]
        else:
            label = 'transition:'+','.join(sorted(allowed[n] for n in influences))
        labels.append(label)
    return labels, dict(profile='complete-limb-influence-triangles-v1', side=side,
        counts=dict(Counter(labels)), authority='none', selected=False,
        scope='render_segmentation_not_surface_depth_or_semantic_ownership')
