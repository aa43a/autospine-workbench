"""Deterministic conservative strategies, separate from binding decisions."""
from hashlib import sha256
from io import BytesIO
import math
import re
from PIL import Image
from ...resolved_project import canonical_sha256
from ..joints.chain_coverage import _components, MAX_PIXELS

PROFILE = 'semantic-alpha-bone-strategy-v1'
FACIAL = {'mouth', 'eye', 'eyes', 'eyebrow', 'eyelash', 'eyewhite', 'irides', 'iris', 'eyelid'}
SECONDARY = {'hair', 'ribbon', 'skirt', 'sleeve'}


def analyze_alpha(layer, data, skeleton):
    if sha256(data).hexdigest() != layer['image_sha256']:
        raise ValueError('planner_image_changed')
    x, y, right, bottom = layer['bbox']
    with Image.open(BytesIO(data)) as image:
        if image.width * image.height > MAX_PIXELS or image.size != (right-x, bottom-y):
            raise ValueError('planner_image_dimensions')
        alpha = image.convert('RGBA').getchannel('A').tobytes()
        w, h = image.size
    components = _components(alpha, w, h, (x, y))
    hits = []
    for bone in skeleton['bones']:
        coordinates = bone['head_xy'] + bone['tail_xy']
        if not all(math.isfinite(v) for v in coordinates):
            raise ValueError('planner_nonfinite_bone')
        count = 0
        for i in range(21):
            px, py = [math.floor(bone['head_xy'][j] + (bone['tail_xy'][j]-bone['head_xy'][j])*i/20)
                      for j in range(2)]
            if 0 <= px-x < w and 0 <= py-y < h and alpha[(py-y)*w+px-x] >= 8:
                count += 1
        if count:
            hits.append({'bone_id': bone['id'], 'opaque_samples': count, 'samples': 21})
    return {'alpha_threshold': 8, 'connectivity': 4, 'component_count': len(components),
            'largest_component_areas': [c['area'] for c in components[:8]],
            'bone_alpha_samples': hits}


def strategy(layer, binding, evidence):
    tokens = set(re.findall(r'[a-z]+', layer['name'].lower()))
    semantic = layer.get('semantic') or ''
    semantic_tokens = set(semantic.split('.'))
    facial = bool((tokens | semantic_tokens) & FACIAL)
    secondary = bool((tokens | semantic_tokens) & SECONDARY)
    meshes = [o for o in binding['options'] if o['mode'] == 'mesh_chain']
    rigid = [o['id'] for o in binding['options'] if o['mode'] == 'rigid']
    reasons = ['semantic_and_options_are_candidates']
    if evidence['component_count'] == 0:
        kind = 'semantic_review'; reasons.append('no_opaque_alpha_support')
    elif facial and secondary:
        kind = 'semantic_review'; reasons.append('conflicting_name_or_semantic_cues')
    elif facial:
        kind = 'facial'; reasons.append('facial_name_or_semantic_cue')
    elif secondary:
        kind = 'secondary_motion'; reasons.append('secondary_name_or_semantic_cue')
    elif tokens & {'objects', 'bottomwear'}:
        kind = 'semantic_review'; reasons.append('ambiguous_object_or_garment')
    elif meshes and not any(len(set(o['bone_ids']) & {h['bone_id'] for h in evidence['bone_alpha_samples']}) >= 2 for o in meshes):
        kind = 'semantic_review'; reasons.append('insufficient_multi_bone_alpha_support')
    elif meshes:
        bilateral = any(len(o['bone_ids']) > 3 for o in meshes)
        kind = 'partition_mesh' if bilateral and evidence['component_count'] > 1 else 'weighted_mesh'
        reasons.append('existing_mesh_chain_options_require_coverage_review')
    elif rigid:
        kind = 'rigid'; reasons.append('existing_rigid_option_requires_visual_review')
    else:
        kind = 'semantic_review'; reasons.append('no_supported_binding_option')
    if evidence['component_count'] > 1:
        reasons.append('disconnected_alpha_does_not_authorize_split')
    return {'strategy': kind, 'reason_codes': reasons,
            'preview': {'rigid_option_ids': rigid, 'status': 'review_required' if rigid else 'blocked'},
            'capability': 'candidate_path_only' if kind in {'rigid', 'weighted_mesh', 'partition_mesh'}
                          else 'not_implemented_by_planner',
            'next_action': {'facial': 'review_facial_anchors_and_attachment_assets',
                            'secondary_motion': 'review_roots_and_future_chain_requirements',
                            'semantic_review': 'review_semantics_and_split_need'}.get(kind, 'review_binding_and_geometry'),
            'confidence': None, 'status': 'needs_review'}


def build(candidate, skeleton, bindings, draft, images, focus=None):
    from ...benchmark.layer_binding_draft import validate_layer_binding_draft
    validate_layer_binding_draft(bindings, draft)
    if bindings['source_skeleton_sha256'] != canonical_sha256(skeleton):
        raise ValueError('planner_skeleton_mismatch')
    layers = candidate['layers']; ids = [r['layer_id'] for r in layers]
    if len(set(ids)) != len(ids) or ids != [r['layer_id'] for r in bindings['bindings']]:
        raise ValueError('planner_layer_inventory')
    if focus is not None and (not focus or len(set(focus)) != len(focus) or not set(focus) <= set(ids)):
        raise ValueError('planner_focus_invalid')
    rows = []
    for layer, binding, record in zip(layers, bindings['bindings'], draft['records']):
        if focus is not None and layer['layer_id'] not in focus:
            continue
        if layer['image_sha256'] != binding['image_sha256'] or layer['bbox'] != binding['bbox']:
            raise ValueError('planner_layer_source_mismatch')
        evidence = analyze_alpha(layer, images[layer['layer_id']], skeleton)
        rows.append({'layer_id': layer['layer_id'], 'name': layer['name'], 'semantic': layer.get('semantic'),
                     'image_sha256': layer['image_sha256'], 'existing_action': record['action'],
                     'evidence': evidence, **strategy(layer, binding, evidence)})
    return {'schema': 'autospine.rig-plan/v1', 'profile': PROFILE, 'character_id': candidate['character_id'],
            'source_candidate_sha256': canonical_sha256(candidate),
            'source_skeleton_sha256': canonical_sha256(skeleton),
            'source_bindings_sha256': canonical_sha256(bindings), 'source_draft_sha256': canonical_sha256(draft),
            'scope': [r['layer_id'] for r in rows], 'layers': rows, 'status': 'needs_review',
            'authority': 'none', 'production_authorized': False}


def validate(candidate, skeleton, bindings, draft, images, document):
    if document != build(candidate, skeleton, bindings, draft, images, document['scope']):
        raise ValueError('planner_replay_mismatch')
    return document
