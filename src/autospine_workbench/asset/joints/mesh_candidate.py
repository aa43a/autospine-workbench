"""Experimental alpha-grid three-bone candidates, separate from historical mesh profiles."""
from copy import deepcopy
import hashlib
import math

from ...alpha_grid_mesh import AlphaGridMeshError, build_alpha_grid_mesh
from ...benchmark.layer_binding_draft import validate_layer_binding_draft
from ...png_rgba import RgbaPngError, decode_rgba_png
from ...resolved_project import canonical_sha256
from .layer_binding import validate_layer_bindings

SCHEMA = 'autospine.weighted-mesh-candidates/v1'
MAX_PIXELS = 32*1024*1024


def _require(condition, reason):
    if not condition:
        raise ValueError('mesh_candidate_'+reason)


def _empty(layer_id, status, reason):
    return {'layer_id': layer_id, 'status': status, 'reason_codes': [reason],
            'vertices_xy': [], 'uvs': [], 'triangles': [], 'weights': [], 'qa': None}


def _image(source, images):
    raw = images.get(source['layer_id'])
    _require(type(raw) is bytes and len(raw) <= 128*1024*1024, 'image_invalid')
    _require(hashlib.sha256(raw).hexdigest() == source['image_sha256'], 'image_changed')
    image_ref = source.get('image')
    _require(type(image_ref) is dict and image_ref.get('sha256') == source['image_sha256']
             and type(image_ref.get('byte_size')) is int and len(raw) == image_ref['byte_size'], 'image_changed')
    try:
        image = decode_rgba_png(raw)
    except RgbaPngError as exc:
        raise ValueError('mesh_candidate_image_invalid') from exc
    box = source['bbox']
    _require((image.width, image.height) == (box[2]-box[0], box[3]-box[1]), 'dimensions_mismatch')
    return image


def _grid_failure(error):
    text = str(error)
    if 'exactly one significant' in text:
        return 'multiple_alpha_components'
    if 'no foreground' in text:
        return 'no_alpha_foreground'
    if 'at least' in text and 'foreground pixels' in text:
        return 'insufficient_alpha_foreground'
    if '99 percent' in text:
        return 'alpha_component_coverage_insufficient'
    return 'alpha_grid_topology_blocked'


def build_mesh_candidate(candidate, assisted, skeleton, bindings, draft, images):
    """Only explicit single-side chain choices run; this is not joint-aware meshing."""
    from .mesh_weights import weights_for_vertices, evaluate_mesh
    validate_layer_bindings(candidate, assisted, skeleton, bindings)
    validate_layer_binding_draft(bindings, draft)
    _require(type(images) is dict, 'images_invalid')
    sources = {row['layer_id']: row for row in candidate['layers']}
    bones = {bone['id']: bone for bone in skeleton['bones']}
    results, pixels = [], 0
    for selected, binding in zip(draft['records'], bindings['bindings']):
        layer_id = selected['layer_id']
        if selected['action'] != 'bind':
            status = 'reviewed_noop' if selected['action'] == 'exclude' else 'blocked'
            reason = 'layer_excluded' if status == 'reviewed_noop' else ('binding_selection_required' if selected['action'] == 'pending' else selected['action'])
            results.append(_empty(layer_id, status, reason))
            continue
        option = next(o for o in binding['options'] if o['id'] == selected['option_id'])
        if option['mode'] == 'rigid':
            results.append(_empty(layer_id, 'reviewed_noop', 'rigid_binding'))
            continue
        if len(option['bone_ids']) == 6:
            results.append(_empty(layer_id, 'blocked', 'bilateral_mesh_pending'))
            continue
        _require(len(option['bone_ids']) == 3, 'unsupported_chain')
        source = sources[layer_id]
        image = _image(source, images)
        pixels += image.width*image.height
        _require(pixels <= MAX_PIXELS, 'resource_limit')
        step = max(4, math.ceil(max(image.width, image.height)/32))
        try:
            grid = build_alpha_grid_mesh(image, grid_step_px=step, alpha_threshold=8)
        except AlphaGridMeshError as exc:
            results.append(_empty(layer_id, 'blocked', _grid_failure(exc)))
            continue
        ox, oy = source['bbox'][:2]
        vertices = [[x+ox, y+oy] for x, y in grid.vertices_xy]
        triangles = [list(row) for row in grid.triangles]
        chain = [bones[key] for key in option['bone_ids']]
        weights = weights_for_vertices(vertices, chain)
        qa = evaluate_mesh(vertices, triangles, weights, chain)
        _require(type(qa) is dict and type(qa.get('passed')) is bool, 'qa_invalid')
        results.append({'layer_id': layer_id, 'status': 'candidate_requires_review' if qa['passed'] else 'blocked',
                        'reason_codes': ['experimental_regular_grid', 'mesh_review_required'] + ([] if qa['passed'] else ['mesh_deformation_qa_failed']),
                        'vertices_xy': vertices, 'uvs': [list(row) for row in grid.uvs], 'triangles': triangles,
                        'weights': weights, 'qa': qa})
    return {'schema': SCHEMA, 'profile': 'alpha-grid-three-bone-v1', 'authority': 'none',
            'production_authorized': False, 'source_bindings_sha256': canonical_sha256(bindings),
            'source_draft_sha256': canonical_sha256(draft), 'layers': results}


def validate_mesh_candidate(candidate, assisted, skeleton, bindings, draft, images, document):
    expected = build_mesh_candidate(candidate, assisted, skeleton, bindings, draft, images)
    if type(document) is not dict or canonical_sha256(document) != canonical_sha256(expected):
        raise ValueError('mesh_candidate_mismatch')
    return deepcopy(expected)
