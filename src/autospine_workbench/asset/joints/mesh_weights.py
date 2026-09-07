"""Experimental distance weights and deterministic three-bone deformation probes."""
import math

MAX_VERTICES = 4096
MAX_TRIANGLES = 8192
ANGLES = (0, 30, -30, 60, -60, 90, -90)


def _require(condition):
    if not condition:
        raise ValueError('mesh_weights_input_invalid')


def _number(value):
    return type(value) in (int, float) and -1e6 <= value <= 1e6 and math.isfinite(value)


def _point(value):
    _require(type(value) is list and len(value) == 2 and all(_number(v) for v in value))
    return value


def _inputs(vertices, bones):
    _require(type(vertices) is list and 3 <= len(vertices) <= MAX_VERTICES)
    for vertex in vertices:
        _point(vertex)
    _require(type(bones) is list and len(bones) == 3)
    ids = set()
    for index, bone in enumerate(bones):
        _require(type(bone) is dict and type(bone.get('id')) is str and 0 < len(bone['id']) <= 200
                 and bone['id'] not in ids and _number(bone.get('world_rotation_degrees')))
        ids.add(bone['id'])
        head, tail = _point(bone.get('head_xy')), _point(bone.get('tail_xy'))
        _require(math.dist(head, tail) >= 1e-7)
        if index:
            _require(bone.get('parent_id') == bones[index-1]['id'])


def _rotate(point, degrees):
    radians = math.radians(degrees)
    cosine, sine = math.cos(radians), math.sin(radians)
    return [point[0]*cosine-point[1]*sine, point[0]*sine+point[1]*cosine]


def _distance_squared(point, start, end):
    delta = [end[i]-start[i] for i in (0, 1)]
    along = sum((point[i]-start[i])*delta[i] for i in (0, 1)) / sum(v*v for v in delta)
    fraction = max(0., min(1., along))
    return sum((point[i]-start[i]-fraction*delta[i])**2 for i in (0, 1))


def weights_for_vertices(vertices, bones):
    """Return inverse-(distance² + 1 px²) weights, not calibrated skinning quality."""
    _inputs(vertices, bones)
    result = []
    for vertex in vertices:
        strengths = [1. / (1. + _distance_squared(vertex, bone['head_xy'], bone['tail_xy'])) for bone in bones]
        total = sum(strengths)
        result.append([{'bone_id': bone['id'], 'weight': strength/total,
                        'local_xy': _rotate([vertex[i]-bone['head_xy'][i] for i in (0, 1)],
                                            -bone['world_rotation_degrees'])}
                       for bone, strength in zip(bones, strengths)])
    return result


def _weights(weights, vertices, bones):
    _require(type(weights) is list and len(weights) == len(vertices))
    valid_ids = {bone['id'] for bone in bones}
    error = 0.
    for row in weights:
        _require(type(row) is list and 1 <= len(row) <= 3)
        seen = set()
        for influence in row:
            _require(type(influence) is dict and set(influence) == {'bone_id', 'weight', 'local_xy'}
                     and type(influence['bone_id']) is str and influence['bone_id'] in valid_ids
                     and influence['bone_id'] not in seen)
            seen.add(influence['bone_id'])
            _require(_number(influence['weight']) and 0 <= influence['weight'] <= 1)
            _point(influence['local_xy'])
        error = max(error, abs(sum(influence['weight'] for influence in row)-1.))
    return error


def _frames(bones, angle):
    # First bone is fixed. Second rotates at its own head; its descendants
    # inherit that rotation, including the third bone's setup offset.
    pivot = bones[1]['head_xy']
    frames = {}
    for index, bone in enumerate(bones):
        head = bone['head_xy']
        if index == 2:
            delta = _rotate([head[i]-pivot[i] for i in (0, 1)], angle)
            head = [pivot[i]+delta[i] for i in (0, 1)]
        frames[bone['id']] = (head, bone['world_rotation_degrees'] + (angle if index else 0))
    return frames


def _deform(weights, frames):
    result = []
    for row in weights:
        vertex = [0., 0.]
        for influence in row:
            head, angle = frames[influence['bone_id']]
            offset = _rotate(influence['local_xy'], angle)
            for i in (0, 1):
                vertex[i] += influence['weight'] * (head[i]+offset[i])
        result.append(vertex)
    return result


def _area(points, triangle):
    a, b, c = [points[index] for index in triangle]
    return ((b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])) / 2.


def evaluate_mesh(vertices, triangles, weights, bones):
    """Replay setup and elbow rotations; all seven probes must pass conservative QA."""
    _inputs(vertices, bones)
    _require(type(triangles) is list and 1 <= len(triangles) <= MAX_TRIANGLES)
    for triangle in triangles:
        _require(type(triangle) is list and len(triangle) == 3
                 and all(type(index) is int and 0 <= index < len(vertices) for index in triangle)
                 and len(set(triangle)) == 3)
    sums = _weights(weights, vertices, bones)
    edges = sorted({tuple(sorted((u, v))) for a, b, c in triangles for u, v in ((a, b), (b, c), (c, a))})
    lengths = [math.dist(vertices[a], vertices[b]) for a, b in edges]
    _require(all(length > 1e-9 for length in lengths))
    areas = [_area(vertices, triangle) for triangle in triangles]
    setup = _deform(weights, _frames(bones, 0))
    error = max(math.dist(a, b) for a, b in zip(vertices, setup))
    probes = []
    for angle in ANGLES:
        deformed = setup if angle == 0 else _deform(weights, _frames(bones, angle))
        inversions = sum(abs(area) <= 1e-9 or _area(deformed, triangle)*area <= 0
                         for triangle, area in zip(triangles, areas))
        stretch = max(math.dist(deformed[a], deformed[b])/length for (a, b), length in zip(edges, lengths))
        probes.append({'id': 'setup' if angle == 0 else f'elbow_{angle:+d}',
                       'inverted_triangle_count': inversions, 'max_edge_stretch': stretch})
    return {'passed': error <= 1e-7 and sums <= 1e-9 and all(
                probe['inverted_triangle_count'] == 0 and probe['max_edge_stretch'] <= 2 for probe in probes),
            'setup_max_error': error, 'weight_sum_max_error': sums, 'probes': probes}
