"""Explicit raw component-grid source acceptance for sleeve annotation v2.

This does not substitute for component_mesh.validate's full source replay. The
onboarding caller must build/replay component masks and ownership before storing.
"""
import math
from .component_mesh import PROFILE


def validate(source, skeleton):
    if (source.get('profile') != PROFILE
            or source.get('texture_policy') != 'isolated_alpha_diagnostic_only'
            or not isinstance(source.get('records'), list)):
        raise ValueError('sleeve_region_mesh_source_invalid')
    bones = {b['id'] for b in skeleton['bones']}
    seen = set()
    for row in source['records']:
        key = row['layer_id'], row['component_id']
        if key in seen:
            raise ValueError('sleeve_region_mesh_inventory_invalid')
        seen.add(key)
        mesh = row['mesh']
        if mesh is None:
            continue
        vertices, triangles = mesh['vertices_xy'], mesh['triangles']
        ids = mesh['bone_ids']
        if (not isinstance(ids, list) or len(set(ids)) != len(ids) or not set(ids) <= bones
                or len(mesh['weights']) != len(vertices) or len(mesh['uvs']) != len(vertices)
                or any(len(p) != 2 or any(type(x) not in (int, float) or not math.isfinite(x)
                    for x in p) for p in vertices + mesh['uvs'])
                or any(len(t) != 3 or len(set(t)) != 3 or any(type(i) is not int
                    or not 0 <= i < len(vertices) for i in t) for t in triangles)):
            raise ValueError('sleeve_region_mesh_geometry_invalid')
        for weights in mesh['weights']:
            if ([w['bone_id'] for w in weights] != ids
                    or any(type(w['weight']) not in (int, float) or not math.isfinite(w['weight'])
                        or not 0 <= w['weight'] <= 1 for w in weights)
                    or any(len(w['local_xy']) != 2 or any(type(x) not in (int, float)
                        or not math.isfinite(x) for x in w['local_xy']) for w in weights)
                    or abs(sum(w['weight'] for w in weights)-1) > 1e-7):
                raise ValueError('sleeve_region_mesh_weights_invalid')
    return source
