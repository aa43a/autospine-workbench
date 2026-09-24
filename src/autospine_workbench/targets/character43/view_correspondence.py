"""Piecewise affine authored view correspondence, independent of rendering.

Coordinates are explicit: source UV and destination UV use top-left origin;
destination points use skeleton world XY. No image or anatomy is inferred.
"""
import math

from ...resolved_project import canonical_sha256


def _points(value, name, unit=False):
    if (not isinstance(value, list) or not 3 <= len(value) <= 10000 or
            any(not isinstance(p, list) or len(p) != 2 or
                any(type(v) not in (int, float) or not math.isfinite(v) for v in p)
                or unit and any(not 0 <= v <= 1 for v in p) for p in value)):
        raise ValueError('view_correspondence_'+name+'_invalid')


def _area(a, b, c):
    return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])


def compile_mapping(mesh, request):
    """Map every existing mesh vertex; return data, never mutate a candidate.

    The control triangulation must cover each complete source mesh triangle.
    A source triangle crossing control cells is rejected: it needs explicit
    subdivision before a piecewise-affine map can be faithfully represented.
    """
    fields = {'mesh_sha256', 'source_uv', 'target_uv', 'target_xy', 'triangles'}
    if not isinstance(request, dict) or set(request) != fields:
        raise ValueError('view_correspondence_request_invalid')
    if request['mesh_sha256'] != canonical_sha256(mesh):
        raise ValueError('view_correspondence_mesh_changed')
    source, target, points = (request[k] for k in ('source_uv', 'target_uv', 'target_xy'))
    for values, name, unit in ((source, 'source_uv', True), (target, 'target_uv', True),
                               (points, 'target_xy', False)):
        _points(values, name, unit)
    if len(source) != len(target) or len(source) != len(points):
        raise ValueError('view_correspondence_control_count')
    triangles = request['triangles']
    if (not isinstance(triangles, list) or not 1 <= len(triangles) <= 20000 or
            any(not isinstance(t, list) or len(t) != 3 or len(set(t)) != 3 or
                any(type(i) is not int or not 0 <= i < len(source) for i in t) for t in triangles)):
        raise ValueError('view_correspondence_triangles_invalid')
    for tri in triangles:
        a = _area(*(source[i] for i in tri))
        b = _area(*(target[i] for i in tri))
        c = _area(*(points[i] for i in tri))
        if abs(a) < 1e-12 or abs(b) < 1e-12 or abs(c) < 1e-12 or a*b <= 0:
            raise ValueError('view_correspondence_degenerate_or_uv_fold')
    # World Y is opposite image V. Require one consistent orientation, allowing
    # either declared world orientation but no local pose fold.
    signs = {_area(*(source[i] for i in t))*_area(*(points[i] for i in t)) > 0 for t in triangles}
    if len(signs) != 1:
        raise ValueError('view_correspondence_pose_fold')
    raw = mesh['uvs']
    if len(raw) % 2:
        raise ValueError('view_correspondence_mesh_uv_invalid')
    vertices = [raw[i:i+2] for i in range(0, len(raw), 2)]
    _points(vertices, 'mesh_uv', True)
    if len(vertices)*len(triangles) > 2000000:
        raise ValueError('view_correspondence_work_budget')
    memberships, mapped_uv, mapped_xy = [], [], []
    for p in vertices:
        found = []
        for index, tri in enumerate(triangles):
            a, b, c = (source[i] for i in tri)
            area = _area(a, b, c)
            weights = [_area(p, b, c)/area, _area(a, p, c)/area, _area(a, b, p)/area]
            if min(weights) >= -1e-10:
                uv = [sum(w*target[i][axis] for w, i in zip(weights, tri)) for axis in (0, 1)]
                xy = [sum(w*points[i][axis] for w, i in zip(weights, tri)) for axis in (0, 1)]
                found.append((index, uv, xy))
        if not found:
            raise ValueError('view_correspondence_uncovered_vertex')
        if any(math.dist(uv, found[0][1]) > 1e-8 or math.dist(xy, found[0][2]) > 1e-6
               for _, uv, xy in found[1:]):
            raise ValueError('view_correspondence_ambiguous_overlap')
        memberships.append({i for i, _, _ in found})
        mapped_uv.extend(found[0][1]); mapped_xy.append(found[0][2])
    flat = mesh['triangles']
    if len(flat) % 3 or any(type(i) is not int or not 0 <= i < len(vertices) for i in flat):
        raise ValueError('view_correspondence_mesh_triangles_invalid')
    for start in range(0, len(flat), 3):
        if not set.intersection(*(memberships[i] for i in flat[start:start+3])):
            raise ValueError('view_correspondence_requires_subdivision')
    return dict(schema='autospine.view-correspondence-result/v1',
                request_sha256=canonical_sha256(request), mesh_sha256=request['mesh_sha256'],
                uvs=mapped_uv, points=mapped_xy, authority='none', selected=False,
                scope='authored_single_pose_not_animation_or_visual_acceptance')
