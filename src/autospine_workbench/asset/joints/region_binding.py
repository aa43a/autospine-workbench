"""Conservative rigid region binding options, without choosing character sides."""
from copy import deepcopy
import math
import re

from ...resolved_project import canonical_sha256
from .reviewed_skeleton import validate_reviewed_skeleton

SCHEMA = 'autospine.region-binding-candidates/v1'
SINGLE = {'body.face': 'head', 'hair.front': 'head', 'hair.side': 'head', 'hair.back': 'head',
          'body.neck': 'neck', 'body.torso': 'chest', 'wear.top': 'chest',
          'wear.skirt': 'pelvis', 'wear.pants': 'pelvis'}
PAIRED = {'body.arm.upper': 'upperarm', 'body.arm.lower': 'forearm', 'body.hand': 'hand',
          'body.leg.upper': 'thigh', 'body.leg.lower': 'calf', 'body.foot': 'foot', 'wear.shoe': 'foot'}


def _require(condition):
    if not condition:
        raise ValueError('region_binding_input_invalid')


def _option(bone, bbox):
    x, y = (bbox[0]+bbox[2])/2, (bbox[1]+bbox[3])/2
    angle = bone['world_rotation_degrees']
    r = math.radians(-angle)
    dx, dy = x-bone['head_xy'][0], y-bone['head_xy'][1]
    return {'bone_id': bone['id'], 'setup_local': {'x': dx*math.cos(r)-dy*math.sin(r),
            'y': dx*math.sin(r)+dy*math.cos(r), 'rotation_degrees': -angle}}


def build_region_bindings(candidate, assisted, skeleton):
    """Caller verifies source pixels; preserve traversal order, never claim draw order."""
    validate_reviewed_skeleton(candidate, assisted, skeleton)
    layers, canvas = candidate.get('layers'), candidate['canvas']
    _require(type(layers) is list and 0 < len(layers) <= 256)
    bones = {row['id']: row for row in skeleton['bones']}
    bindings, seen, previous = [], set(), -1
    for layer in layers:
        _require(type(layer) is dict and type(layer.get('layer_id')) is str and layer['layer_id'] not in seen)
        seen.add(layer['layer_id'])
        traversal = layer.get('traversal_index')
        _require(type(traversal) is int and traversal > previous)
        previous = traversal
        digest, box, observed = layer.get('image_sha256'), layer.get('bbox'), layer.get('observed')
        _require(type(digest) is str and re.fullmatch('[0-9a-f]{64}', digest) is not None)
        _require(type(box) is list and len(box) == 4 and all(type(v) is int for v in box)
                 and box[0] <= box[2] and box[1] <= box[3])
        _require(type(observed) is dict and type(observed.get('empty')) is bool and type(observed.get('visible')) is bool)
        semantic = layer.get('semantic')
        _require(semantic is None or type(semantic) is str)
        reasons = []
        if skeleton['status'] == 'blocked':
            reasons.append('skeleton_blocked')
        if observed['empty'] or box[0] == box[2] or box[1] == box[3]:
            reasons.append('empty_layer')
        if not observed['visible']:
            reasons.append('hidden_layer')
        if box[0] < 0 or box[1] < 0 or box[2] > canvas[0] or box[3] > canvas[1]:
            reasons.append('layer_outside_canvas')
        if semantic not in SINGLE and semantic not in PAIRED:
            reasons.append('semantic_binding_unsupported')
        options, suggestion = [], None
        if not reasons:
            ids = [SINGLE[semantic]] if semantic in SINGLE else [PAIRED[semantic]+'_l', PAIRED[semantic]+'_r']
            _require(all(identifier in bones for identifier in ids))
            options = [_option(bones[identifier], box) for identifier in ids]
            suggestion = ids[0] if len(ids) == 1 else None
            reasons = ['semantic_roles_unreviewed', 'region_binding_requires_review']
            if len(ids) > 1:
                reasons.append('character_side_requires_review')
        bindings.append({'layer_id': layer['layer_id'], 'image_sha256': digest, 'bbox': deepcopy(box),
                         'bone_options': options, 'suggested_bone_id': suggestion,
                         'status': 'needs_review' if options else 'blocked', 'reason_codes': reasons})
    return {'schema': SCHEMA, 'candidate_sha256': canonical_sha256(candidate),
            'source_skeleton_sha256': canonical_sha256(skeleton), 'profile': 'conservative-region-binding-v1',
            'authority': 'none', 'production_authorized': False, 'status': 'blocked' if skeleton['status'] == 'blocked' else 'needs_review',
            'canvas': deepcopy(canvas), 'bindings': bindings}


def validate_region_bindings(candidate, assisted, skeleton, document):
    expected = build_region_bindings(candidate, assisted, skeleton)
    if type(document) is not dict or canonical_sha256(document) != canonical_sha256(expected):
        raise ValueError('region_binding_mismatch')
    return deepcopy(expected)
