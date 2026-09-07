"""Bounded four-connected alpha diagnostics for unweighted limb-chain choices."""
from copy import deepcopy
import hashlib
from io import BytesIO
import math

from ...resolved_project import canonical_sha256
from .layer_binding import validate_layer_bindings

PARAMETERS = {'alpha_threshold': 8, 'connectivity': 4, 'samples_per_bone': 21,
              'radius_px': 3, 'low_coverage_ratio': .5, 'max_reported_components': 32}
MAX_RUNS = 131072
MAX_PIXELS = 32*1024*1024


def _require(condition, reason='input_invalid'):
    if not condition:
        raise ValueError('chain_coverage_'+reason)


def _components(alpha, width, height, offset):
    """Row interval overlap gives four-connectivity in O(pixels+runs α(runs))."""
    runs, parents, previous = [], [], []
    def root(label):
        while parents[label] != label:
            parents[label] = parents[parents[label]]
            label = parents[label]
        return label
    for y in range(height):
        current, x, cursor = [], 0, 0
        while x < width:
            if alpha[y*width+x] < 8:
                x += 1
                continue
            start = x
            while x+1 < width and alpha[y*width+x+1] >= 8:
                x += 1
            _require(len(runs) < MAX_RUNS, 'resource_limit')
            label = len(runs)
            parents.append(label)
            while cursor < len(previous) and previous[cursor][1] < start:
                cursor += 1
            index = cursor
            while index < len(previous) and previous[index][0] <= x:
                a, b = root(label), root(previous[index][2])
                if a != b:
                    parents[max(a, b)] = min(a, b)
                index += 1
            runs.append((y, start, x, label))
            current.append((start, x, label))
            x += 1
        previous = current
    groups = {}
    for y, left, right, label in runs:
        key, area = root(label), right-left+1
        row = groups.setdefault(key, [0, left, y, right+1, y+1, 0, 0])
        row[0] += area
        row[1], row[2], row[3], row[4] = min(row[1], left), min(row[2], y), max(row[3], right+1), max(row[4], y+1)
        row[5] += (left+right)*area/2
        row[6] += y*area
    ox, oy = offset
    components = [{'id': key, 'area': r[0], 'bbox': [r[1]+ox, r[2]+oy, r[3]+ox, r[4]+oy],
                   'centroid': [r[5]/r[0]+ox, r[6]/r[0]+oy]} for key, r in groups.items()]
    components.sort(key=lambda c: (-c['area'], c['id']))
    return components


def _coverage(bone, alpha, width, height, offset):
    covered = 0
    ox, oy = offset
    for tick in range(21):
        point = [a+(b-a)*tick/20 for a, b in zip(bone['head_xy'], bone['tail_xy'])]
        x, y = point[0]-ox, point[1]-oy
        hit = False
        for py in range(max(0, math.ceil(y-3)), min(height-1, math.floor(y+3))+1):
            for px in range(max(0, math.ceil(x-3)), min(width-1, math.floor(x+3))+1):
                if (px-x)**2+(py-y)**2 <= 9 and alpha[py*width+px] >= 8:
                    hit = True
                    break
            if hit:
                break
        covered += hit
    return {'bone_id': bone['id'], 'sample_count': 21, 'covered_samples': covered, 'coverage_ratio': covered/21}


def build_chain_coverage(candidate, assisted, skeleton, bindings, images):
    """Caller verifies complete source closure; only mesh-choice rasters are analyzed."""
    validate_layer_bindings(candidate, assisted, skeleton, bindings)
    _require(type(images) is dict)
    try:
        from PIL import Image
    except ImportError as exc:
        raise ValueError('chain_coverage_pillow_required') from exc
    sources = {r['layer_id']: r for r in candidate['layers']}
    bones = {b['id']: b for b in skeleton['bones']}
    result, pixels = [], 0
    for row in bindings['bindings']:
        options = [o for o in row['options'] if o['mode'] == 'mesh_chain']
        if not options:
            continue
        source, raw = sources[row['layer_id']], images.get(row['layer_id'])
        _require(type(raw) is bytes and len(raw) <= 128*1024*1024, 'image_invalid')
        _require(hashlib.sha256(raw).hexdigest() == source['image_sha256'], 'image_changed')
        if 'image' in source:
            _require(len(raw) == source['image']['byte_size'] and source['image']['sha256'] == source['image_sha256'], 'image_changed')
        box = source['bbox']
        try:
            with Image.open(BytesIO(raw)) as image:
                _require(image.format == 'PNG' and image.mode == 'RGBA', 'image_invalid')
                width, height = image.size
                _require((width, height) == (box[2]-box[0], box[3]-box[1]), 'dimensions_mismatch')
                _require(0 < width <= 4096 and 0 < height <= 4096, 'resource_limit')
                pixels += width*height
                _require(pixels <= MAX_PIXELS, 'resource_limit')
                alpha = image.getchannel('A').tobytes()
        except (OSError, SyntaxError) as exc:
            raise ValueError('chain_coverage_image_invalid') from exc
        components = _components(alpha, width, height, (box[0], box[1]))
        retained, omitted = components[:32], components[32:]
        total = sum(c['area'] for c in components)
        reasons = ['diagnostic_only_not_weights', 'coverage_requires_review']
        if len(components) > 1:
            reasons.append('multiple_components')
        if not total:
            reasons.append('no_alpha')
        analyzed = []
        for option in options:
            rows = [_coverage(bones[bone_id], alpha, width, height, (box[0], box[1])) for bone_id in option['bone_ids']]
            flags = ['coverage_requires_review']
            if any(b['coverage_ratio'] < .5 for b in rows):
                flags.append('low_bone_alpha_coverage')
            analyzed.append({'option_id': option['id'], 'bones': rows, 'reason_codes': flags})
        result.append({'layer_id': row['layer_id'], 'alpha_pixel_count': total, 'component_count': len(components),
                       'omitted_component_count': len(omitted), 'omitted_alpha_pixel_count': sum(c['area'] for c in omitted),
                       'components': retained, 'options': analyzed, 'reason_codes': reasons})
    return {'schema': 'autospine.chain-coverage/v1', 'profile': 'alpha-chain-coverage-v1',
            'authority': 'none', 'production_authorized': False, 'source_bindings_sha256': canonical_sha256(bindings),
            'parameters': deepcopy(PARAMETERS), 'layers': result}


def validate_chain_coverage(candidate, assisted, skeleton, bindings, images, document):
    expected = build_chain_coverage(candidate, assisted, skeleton, bindings, images)
    if type(document) is not dict or canonical_sha256(document) != canonical_sha256(expected):
        raise ValueError('chain_coverage_mismatch')
    return deepcopy(expected)
