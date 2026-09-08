"""Conservative head-detail options without changing historical binding profiles."""
from copy import deepcopy
import re
import unicodedata

from ...resolved_project import canonical_sha256
from .layer_binding import BLOCKERS, build_layer_bindings
from .region_binding import _option

PROFILE = 'rigid-name-completion-v3'
HEAD_NAMES = {'eyebrow', 'ears', 'ear', 'mouth', 'nose', 'eyewhite',
              'irides', 'iris', 'eyelash', 'headwear'}


def build_completion(candidate, assisted, skeleton):
    result = build_layer_bindings(candidate, assisted, skeleton)
    head = next(b for b in skeleton['bones'] if b['id'] == 'head')
    for source, row in zip(candidate['layers'], result['bindings']):
        if row['options'] or BLOCKERS.intersection(row['reason_codes']):
            continue
        name = ' '.join(unicodedata.normalize('NFKC', source['name']).lower().split())
        if re.sub(r'-[lr]$', '', name).strip() not in HEAD_NAMES:
            continue
        row.update(options=[{'id': 'rigid:head', 'mode': 'rigid', 'bone_ids': ['head'],
                             'setup_local': _option(head, row['bbox'])['setup_local']}],
                   suggested_option_id='rigid:head', status='needs_review',
                   reason_codes=['head_detail_name_candidate', 'visual_parent_review_required'])
    result['profile'] = PROFILE
    return result


def validate_completion(candidate, assisted, skeleton, document):
    expected = build_completion(candidate, assisted, skeleton)
    if canonical_sha256(document) != canonical_sha256(expected):
        raise ValueError('binding_completion_mismatch')
    return deepcopy(expected)


def inherit_unchanged(base, old_draft, completed):
    from ...benchmark.layer_binding_draft import build_layer_binding_draft, validate_layer_binding_draft
    validate_layer_binding_draft(base, old_draft)
    if base['profile'] != 'rigid-or-limb-chain-v2' or completed['profile'] != PROFILE \
            or any(base[k] != completed[k] for k in ('candidate_sha256', 'source_skeleton_sha256')) \
            or [r['layer_id'] for r in base['bindings']] != [r['layer_id'] for r in completed['bindings']]:
        raise ValueError('binding_completion_source_mismatch')
    draft = build_layer_binding_draft(completed)
    for old, new, record, target in zip(base['bindings'], completed['bindings'],
                                       old_draft['records'], draft['records']):
        if old == new:
            target.update(deepcopy(record))
        elif record['action'] != 'pending':
            raise ValueError('binding_completion_changed_reviewed_layer')
    return validate_layer_binding_draft(completed, draft)
