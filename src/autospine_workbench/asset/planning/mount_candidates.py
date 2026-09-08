"""Semantic hypotheses with observed alpha-to-anchor distances, never decisions."""
from hashlib import sha256
from io import BytesIO
import math
import re
from PIL import Image
from ...resolved_project import canonical_sha256
from .rig_planner import analyze_alpha

PROFILE = 'garment-prop-wing-mount-v1'
RULES = {
    'garment': (['wear.skirt', 'wear.pants'], [('pelvis', 'head_xy')]),
    'prop': (['accessory.held', 'accessory.attached', 'unknown'],
             [('hand_l', 'head_xy'), ('hand_r', 'head_xy'), ('chest', 'head_xy'), ('pelvis', 'head_xy')]),
    'wing': (['accessory.wing'], [('chest', 'head_xy'), ('spine', 'head_xy')]),
}


def category(layer):
    tokens = set(re.findall(r'[a-z]+', layer['name'].lower()))
    semantic = layer.get('semantic') or ''
    matches = []
    if tokens & {'bottomwear', 'skirt', 'pants'} or semantic in {'wear.skirt', 'wear.pants'}:
        matches.append('garment')
    if tokens & {'objects', 'object', 'prop'} or semantic in {'accessory.held', 'accessory.attached'}:
        matches.append('prop')
    if tokens & {'wing', 'wings'} or semantic == 'accessory.wing':
        matches.append('wing')
    return matches[0] if len(matches) == 1 else ('conflict' if matches else None)


def suggest(layer, raw, skeleton, character_height):
    kind = category(layer)
    if kind is None:
        return None
    if not math.isfinite(character_height) or character_height <= 0:
        raise ValueError('mount_character_height_invalid')
    evidence = analyze_alpha(layer, raw, skeleton)
    bones = {b['id']: b for b in skeleton['bones']}
    if len(bones) != len(skeleton['bones']):
        raise ValueError('mount_duplicate_bone')
    x, y, _, _ = layer['bbox']
    with Image.open(BytesIO(raw)) as image:
        alpha = image.convert('RGBA').getchannel('A'); width = image.width
        points = [(x+i%width+.5, y+i//width+.5) for i,a in enumerate(alpha.tobytes()) if a >= 8]
    hypotheses, targets = RULES.get(kind, (['unknown'], []))
    options = []; missing = []
    for bone_id, endpoint in targets:
        if bone_id not in bones:
            missing.append(bone_id); continue
        anchor = bones[bone_id][endpoint]
        nearest = min(points, key=lambda p: (p[0]-anchor[0])**2+(p[1]-anchor[1])**2) if points else None
        distance = math.dist(anchor, nearest) if nearest else None
        options.append({'bone_id': bone_id, 'endpoint': endpoint, 'anchor_xy': list(anchor),
            'nearest_alpha_xy': list(nearest) if nearest else None,
            'distance_px': round(distance, 6) if distance is not None else None,
            'normalized_distance': round(distance/character_height, 8) if distance is not None else None,
            'nearby': distance <= .05*character_height if distance is not None else False})
    supported = [o for o in options if o['nearby']]
    reasons = ['name_semantic_hypotheses_unreviewed', 'proximity_is_not_attachment_proof']
    if kind == 'garment': reasons.append('skirt_vs_pants_requires_visual_review')
    if kind == 'wing': reasons.append('wing_root_may_be_occluded')
    if kind == 'prop': reasons.append('held_vs_attached_requires_contact_review')
    if kind == 'conflict': reasons.append('conflicting_semantic_cues')
    if not points: reasons.append('no_opaque_alpha_support')
    elif not supported: reasons.append('no_nearby_mount_anchor')
    elif len(supported) > 1: reasons.append('multiple_nearby_mount_anchors')
    if missing: reasons.append('required_bones_missing')
    return {'layer_id': layer['layer_id'], 'name': layer['name'], 'category': kind,
            'image_sha256': sha256(raw).hexdigest(), 'semantic_hypotheses': hypotheses,
            'mount_options': options, 'missing_bones': missing, 'alpha_evidence': evidence,
            'reason_codes': reasons, 'confidence': None, 'selected_option': None, 'status': 'needs_review'}


def build(candidate, skeleton, plan, images):
    if (plan['source_candidate_sha256'] != canonical_sha256(candidate)
            or plan['source_skeleton_sha256'] != canonical_sha256(skeleton)
            or plan['authority'] != 'none' or plan['production_authorized'] is not False):
        raise ValueError('mount_source_mismatch')
    ids = [r['layer_id'] for r in candidate['layers']]
    if ids != plan['scope'] or len(set(ids)) != len(ids):
        raise ValueError('mount_full_source_required')
    height = max(r['bbox'][3] for r in candidate['layers'])-min(r['bbox'][1] for r in candidate['layers'])
    rows = []
    for layer in candidate['layers']:
        row = suggest(layer, images[layer['layer_id']], skeleton, height)
        if row is not None: rows.append(row)
    return {'schema': 'autospine.mount-candidates/v1', 'profile': PROFILE,
            'source_plan_sha256': canonical_sha256(plan), 'character_id': candidate['character_id'],
            'character_height_px': height, 'parameters': {'alpha_threshold':8, 'nearby_height_ratio':.05},
            'layers': rows, 'status':'needs_review', 'authority':'none', 'production_authorized':False}


def validate(candidate, skeleton, plan, images, document):
    if document != build(candidate, skeleton, plan, images):
        raise ValueError('mount_replay_mismatch')
    return document
