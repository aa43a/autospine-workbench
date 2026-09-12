"""Versioned front/back topwear candidates, without automatic approval."""
from copy import deepcopy
import unicodedata

from ...resolved_project import canonical_sha256
from ...benchmark.layer_binding_draft import build_layer_binding_draft, validate_layer_binding_draft
from .rigid_completion import build_completion as previous_completion
from .layer_binding import BLOCKERS
from .region_binding import _option

PROFILE = 'rigid-garment-completion-v5'
PREVIOUS = {'rigid-or-limb-chain-v2', 'rigid-name-completion-v3', 'rigid-detail-completion-v4'}


def build_completion(candidate, assisted, skeleton):
    result = previous_completion(candidate, assisted, skeleton)
    bones = {bone['id']: bone for bone in skeleton['bones']}
    for source, row in zip(candidate['layers'], result['bindings']):
        if row['options'] or BLOCKERS.intersection(row['reason_codes']):
            continue
        name = ' '.join(unicodedata.normalize('NFKC', source['name']).lower().split())
        if name not in {'topwear-front', 'topwear-back'} or source.get('semantic') not in (None, 'wear.top'):
            continue
        if 'chest' not in bones:
            raise ValueError('binding_garment_topology_missing')
        row.update(options=[dict(id='rigid:chest', mode='rigid', bone_ids=['chest'],
                                setup_local=_option(bones['chest'], row['bbox'])['setup_local'])],
                   suggested_option_id='rigid:chest', status='needs_review',
                   reason_codes=['garment_name_candidate', 'visual_parent_review_required',
                                 'attachment_extent_requires_review'])
    result['profile'] = PROFILE
    return result


def validate_completion(candidate, assisted, skeleton, document):
    expected = build_completion(candidate, assisted, skeleton)
    if canonical_sha256(document) != canonical_sha256(expected):
        raise ValueError('binding_completion_mismatch')
    return deepcopy(expected)


def inherit_unchanged(base, old_draft, completed):
    validate_layer_binding_draft(base, old_draft)
    if base['profile'] not in PREVIOUS or completed['profile'] != PROFILE or any(
            base[key] != completed[key] for key in ('candidate_sha256', 'source_skeleton_sha256')) or (
            [row['layer_id'] for row in base['bindings']] != [row['layer_id'] for row in completed['bindings']]):
        raise ValueError('binding_completion_source_mismatch')
    draft = build_layer_binding_draft(completed)
    for old, new, record, target in zip(base['bindings'], completed['bindings'], old_draft['records'], draft['records']):
        if record['action'] == 'bind':
            selected = next(option for option in old['options'] if option['id'] == record['option_id'])
            if selected not in new['options']:
                raise ValueError('binding_completion_changed_reviewed_layer')
        target.update(deepcopy(record))
    return validate_layer_binding_draft(completed, draft)
