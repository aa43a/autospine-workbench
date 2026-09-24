"""Explicit normalized-UV registration for isolated regional artwork trials.

This is not the same-canvas artwork-return API. A valid affine registration is
only a coordinate hypothesis; it does not establish visual correspondence.
"""
from copy import deepcopy
import math
from .material_region_scene import build as split_region


def build(document, plan, texture, affine):
    if (not isinstance(affine, list) or len(affine) != 6 or
            any(type(v) not in (float, int) or not math.isfinite(v) for v in affine)):
        raise ValueError('registered_material_affine_invalid')
    a, b, c, d, tx, ty = affine
    if a*d-b*c <= 1e-10:
        raise ValueError('registered_material_fold_or_collapse')
    # Reuse disjoint geometry/alpha splitting; its original-UV policy is internal
    # to that operation. Only the replacement's UVs are changed afterwards.
    result, report = split_region(document, plan, texture)
    slot = report['replacement_slot']
    mesh = result['skins'][0]['attachments'][slot][slot]
    original = mesh['uvs'][:]
    used = set(mesh['triangles'])
    for index in used:
        u, v = original[2*index:2*index+2]
        point = [a*u+b*v+tx, c*u+d*v+ty]
        if any(x < 0 or x > 1 for x in point):
            raise ValueError('registered_material_outside_texture')
        mesh['uvs'][2*index:2*index+2] = point
    report = deepcopy(report)
    report.update(profile='registered-material-region-experiment-v1',
                  uv_policy='explicit_normalized_uv_affine', uv_affine=affine[:],
                  visual_correspondence='unverified', production_authorized=False)
    return result, report
