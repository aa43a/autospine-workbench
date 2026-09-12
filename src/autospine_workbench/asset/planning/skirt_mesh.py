"""Version-neutral, fixed-waist skirt mesh candidates; no review or physics authority."""
from bisect import bisect_left, bisect_right
import json
import math


MAX_PIXELS = 4_000_000
MAX_AXIS = 16_384
MAX_CELLS = 100_000


class SkirtMeshError(ValueError):
    """Stable machine-readable rejection, also usable as an ordinary ValueError."""

    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _raster(alpha):
    if not isinstance(alpha, (list, tuple)) or not alpha:
        raise SkirtMeshError('skirt_alpha_dimensions')
    height = len(alpha)
    if not isinstance(alpha[0], (list, tuple)) or not alpha[0]:
        raise SkirtMeshError('skirt_alpha_dimensions')
    width = len(alpha[0])
    if max(width, height) > MAX_AXIS or width * height > MAX_PIXELS:
        raise SkirtMeshError('skirt_resource_limit')
    mask = bytearray(width * height)
    xmin, ymin, xmax, ymax, count = width, height, 0, 0, 0
    for y, row in enumerate(alpha):
        if not isinstance(row, (list, tuple)) or len(row) != width:
            raise SkirtMeshError('skirt_alpha_dimensions')
        for x, value in enumerate(row):
            if type(value) is not int or not 0 <= value <= 255:
                raise SkirtMeshError('skirt_alpha_value')
            if value:
                mask[y * width + x] = 1
                xmin, ymin = min(xmin, x), min(ymin, y)
                xmax, ymax = max(xmax, x + 1), max(ymax, y + 1)
                count += 1
    if not count:
        raise SkirtMeshError('skirt_alpha_empty')
    return width, height, mask, [xmin, ymin, xmax, ymax], count


def _components(mask, width):
    # One bounded byte array, with each occupied pixel pushed only once.
    unseen = bytearray(mask)
    count = 0
    for seed, value in enumerate(unseen):
        if not value:
            continue
        count += 1
        stack = [seed]
        unseen[seed] = 0
        while stack:
            index = stack.pop()
            x = index % width
            neighbors = []
            if x:
                neighbors.append(index - 1)
            if x + 1 < width:
                neighbors.append(index + 1)
            if index >= width:
                neighbors.append(index - width)
            if index + width < len(mask):
                neighbors.append(index + width)
            for neighbor in neighbors:
                if unseen[neighbor]:
                    unseen[neighbor] = 0
                    stack.append(neighbor)
    return count


def _smooth(t):
    t = min(1.0, max(0.0, t))
    return t * t * (3.0 - 2.0 * t)


def _weights(x, y, roots, waist, bottom):
    if y <= waist:
        return [{'bone': 'pelvis', 'weight': 1.0}]
    position = min(2.0, max(0.0, (x - roots[0]) / (roots[2] - roots[0]) * 2))
    left = min(1, int(position))
    fraction = position - left
    chains = [(left, 1.0 - fraction), (left + 1, fraction)]
    t = (y - waist) / (bottom - waist)
    if t <= 0.5:
        blend = _smooth(t * 2)
        values = [('pelvis', 1.0 - blend)]
        values.extend((f'skirt_{i}_upper', blend * weight) for i, weight in chains)
    else:
        blend = _smooth(t * 2 - 1)
        values = [(f'skirt_{i}_{part}', weight * factor)
                  for i, weight in chains
                  for part, factor in [('upper', 1.0 - blend), ('lower', blend)]]
    result = [{'bone': bone, 'weight': weight} for bone, weight in values if weight > 0]
    total = sum(entry['weight'] for entry in result)
    for entry in result:
        entry['weight'] /= total
    # Make Python's ordered sum exactly one, without adding a fifth influence.
    result[-1]['weight'] = 1.0 - sum(entry['weight'] for entry in result[:-1])
    return [entry for entry in result if entry['weight'] > 0]


def build_skirt_mesh(alpha, waist_y, step=32):
    """Build a conservative mesh in local image pixels (x right, y down).

    Alpha is a rectangular list/tuple of integer rows, 0..255. Pixels occupy
    unit squares, not isolated centers. Bounds and UVs use the complete canvas.
    A two-pixel-high waist band must contain three distinct supported columns.
    Retained cells may include transparent pixels; holes are not filled in the
    source texture. Every source alpha square is covered by the output triangles.
    All results remain candidates requiring review, even when connected.
    """
    if (type(waist_y) not in (int, float) or
            (isinstance(waist_y, int) and abs(waist_y) > MAX_AXIS) or
            not math.isfinite(waist_y)):
        raise SkirtMeshError('skirt_waist_nonfinite')
    if type(step) is not int or not 1 <= step <= MAX_AXIS:
        raise SkirtMeshError('skirt_step_invalid')
    width, height, mask, bounds, pixel_count = _raster(alpha)
    xmin, ymin, xmax, bottom = bounds
    waist = float(waist_y)
    if not ymin <= waist < bottom:
        raise SkirtMeshError('skirt_waist_outside_alpha')
    band_start = max(0, math.floor(waist - 1))
    band_end = min(height, math.ceil(waist + 1))
    support = [x for x in range(xmin, xmax)
               if any(mask[y * width + x] for y in range(band_start, band_end))]
    if len(support) < 3:
        raise SkirtMeshError('skirt_waist_support_insufficient')
    roots = [support[0] + 0.5, (support[0] + support[-1] + 1) / 2, support[-1] + 0.5]
    mid = (waist + bottom) / 2
    if not waist < mid < bottom:
        raise SkirtMeshError('skirt_height_degenerate')
    xs = list(range(xmin, xmax, step)) + [xmax]
    ys = sorted(set(list(range(ymin, bottom, step)) + [waist, mid, bottom]))
    if (len(xs) - 1) * (len(ys) - 1) > MAX_CELLS:
        raise SkirtMeshError('skirt_resource_limit')
    occupied = set()
    # Fractional waist/mid rows can split a pixel: retain every intersected cell.
    for y in range(ymin, bottom):
        row_start = max(0, bisect_right(ys, y) - 1)
        row_end = bisect_left(ys, y + 1)
        for x in range(xmin, xmax):
            if mask[y * width + x]:
                column = min(len(xs) - 2, (x - xmin) // step)
                occupied.update((row, column) for row in range(row_start, row_end))
    vertices, triangles, lookup = [], [], {}
    for row, column in sorted(occupied):
        corners = [(xs[column], ys[row]), (xs[column + 1], ys[row]),
                   (xs[column + 1], ys[row + 1]), (xs[column], ys[row + 1])]
        indices = []
        for point in corners:
            if point not in lookup:
                lookup[point] = len(vertices)
                vertices.append([float(point[0]), float(point[1])])
            indices.append(lookup[point])
        a, b, c, d = indices
        triangles.extend([[a, b, c], [a, c, d]])
    components = _components(mask, width)
    reasons = ['candidate_unreviewed']
    if components > 1:
        reasons.append('disconnected_alpha')
    if any(not any(mask[y * width + int(root)] for y in range(band_start, band_end)) for root in roots):
        reasons.append('helper_root_over_alpha_gap')
    return {
        'schema': 'autospine.skirt-mesh-candidate/v1',
        'authority': 'none',
        'profile': 'fixed-waist-skirt-mesh-candidate-v1',
        'vertices': vertices,
        'uvs': [[x / width, y / height] for x, y in vertices],
        'triangles': triangles,
        'influences': [_weights(x, y, roots, waist, bottom) for x, y in vertices],
        'helper_chains': [{'id': f'skirt_{i}', 'points': [[root, waist], [root, mid], [root, float(bottom)]]}
                          for i, root in enumerate(roots)],
        'coverage': {'canvas_size': [width, height], 'alpha_bbox': bounds,
                     'alpha_pixels': pixel_count, 'covered_alpha_pixels': pixel_count,
                     'retained_cells': len(occupied), 'alpha_components': components,
                     'method': 'all_intersected_pixel_cells'},
        'review_required': True,
        'review_reasons': reasons,
    }


def validate_skirt_mesh(alpha, waist_y, candidate, step=32):
    """Replay the complete geometry and weight contract against exact source alpha."""
    expected = build_skirt_mesh(alpha, waist_y, step)
    try:
        encode = lambda value: json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)
        equal = encode(candidate) == encode(expected)
    except (TypeError, ValueError):
        equal = False
    if not equal:
        raise SkirtMeshError('skirt_candidate_source_mismatch')
    return candidate
