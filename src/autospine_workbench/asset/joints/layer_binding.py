"""Versioned rigid or limb-chain choices; chain selection never supplies weights."""
from copy import deepcopy
import re
import unicodedata

from ...resolved_project import canonical_sha256
from .region_binding import build_region_bindings

SCHEMA = 'autospine.layer-binding-candidates/v2'
CHAINS = {'arm': ('upperarm', 'forearm', 'hand'), 'leg': ('thigh', 'calf', 'foot')}
NAMES = {'handwear': 'arm', 'arm': 'arm', 'sleeve': 'arm', 'legwear': 'leg', 'leg': 'leg'}
BLOCKERS = {'skeleton_blocked', 'empty_layer', 'hidden_layer', 'layer_outside_canvas'}


def build_layer_bindings(candidate, assisted, skeleton):
    """Preserve rigid-v1 results; offer complete chains as unweighted hypotheses."""
    rigid = build_region_bindings(candidate, assisted, skeleton)
    bones = {b['id']: b for b in skeleton['bones']}
    bindings = []
    for source, row in zip(candidate['layers'], rigid['bindings']):
        options = [{'id': 'rigid:'+o['bone_id'], 'mode': 'rigid', 'bone_ids': [o['bone_id']],
                    'setup_local': deepcopy(o['setup_local'])} for o in row['bone_options']]
        suggestion = 'rigid:'+row['suggested_bone_id'] if row['suggested_bone_id'] else None
        reasons = list(row['reason_codes'])
        name = source.get('name')
        if type(name) is not str:
            raise ValueError('layer_binding_name_invalid')
        normalized = ' '.join(unicodedata.normalize('NFKC', name).lower().split())
        match = re.fullmatch(r'(.+)-([lr])', normalized)
        base, side = (match[1].strip(), match[2]) if match else (normalized, None)
        chain = NAMES.get(base)
        if chain and not BLOCKERS.intersection(reasons):
            for suffix in ('l', 'r'):
                ids = [bone+'_'+suffix for bone in CHAINS[chain]]
                if any(key not in bones for key in ids) or any(bones[ids[i]]['parent_id'] != ids[i-1] for i in (1, 2)):
                    raise ValueError('layer_binding_chain_topology_invalid')
                options.append({'id': f'mesh_chain:{suffix}:{chain}', 'mode': 'mesh_chain',
                                'bone_ids': ids, 'setup_local': None})
            reasons = [code for code in reasons if code != 'semantic_binding_unsupported']
            reasons += ['mesh_weights_required', 'coverage_review_required']
            if side:
                suggestion = f'mesh_chain:{side}:{chain}'
                reasons.append('name_side_unreviewed')
            else:
                suggestion = None
                options.append({'id': f'mesh_chain:bilateral:{chain}', 'mode': 'mesh_chain',
                                'bone_ids': [bone+'_'+suffix for suffix in ('l', 'r') for bone in CHAINS[chain]],
                                'setup_local': None})
                reasons.append('bilateral_coverage_requires_review')
                if 'character_side_requires_review' not in reasons:
                    reasons.append('character_side_requires_review')
        bindings.append({'layer_id': row['layer_id'], 'image_sha256': row['image_sha256'],
                         'bbox': deepcopy(row['bbox']), 'options': options, 'suggested_option_id': suggestion,
                         'status': 'needs_review' if options else 'blocked', 'reason_codes': reasons})
    return {'schema': SCHEMA, 'profile': 'rigid-or-limb-chain-v2', 'authority': 'none',
            'production_authorized': False, 'candidate_sha256': canonical_sha256(candidate),
            'source_skeleton_sha256': canonical_sha256(skeleton), 'canvas': deepcopy(candidate['canvas']),
            'status': rigid['status'], 'bindings': bindings}


def validate_layer_bindings(candidate, assisted, skeleton, document):
    expected = build_layer_bindings(candidate, assisted, skeleton)
    if type(document) is not dict or canonical_sha256(document) != canonical_sha256(expected):
        raise ValueError('layer_binding_mismatch')
    return deepcopy(expected)
