"""Translate explicitly declared accessory roots with an owner's planar warp."""
from .torso_projection_candidate import inverse, multiply, point


def displacements(bones, baseline, warped, owner, roots):
    parents = {bone['name']: bone.get('parent') for bone in bones}
    roots = set(roots)
    if not roots or owner not in parents or not roots <= parents.keys() or owner in roots:
        raise ValueError('attachment_transport_roots_invalid')
    # Root declarations are disjoint. An already warped owner descendant must not
    # receive the same warp twice.
    for root in roots:
        parent = parents[root]
        seen = {root}
        while parent:
            if parent in seen or parent in roots or parent == owner:
                raise ValueError('attachment_transport_root_ancestry')
            seen.add(parent)
            parent = parents[parent]
    delta = multiply(warped[owner], inverse(baseline[owner]))
    shifts = {}
    for bone in bones:
        name = bone['name']
        if name in roots:
            x, y = baseline[name][4:]
            nx, ny = point(delta, x, y)
            shifts[name] = (nx-x, ny-y)
        elif bone.get('parent') in shifts:
            shifts[name] = shifts[bone['parent']]
    return shifts
