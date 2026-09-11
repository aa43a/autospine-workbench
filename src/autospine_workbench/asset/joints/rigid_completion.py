"""Add explicit shoe options while preserving historical head-detail candidates."""
from copy import deepcopy
import re
import unicodedata

from ...resolved_project import canonical_sha256
from ...benchmark.layer_binding_draft import build_layer_binding_draft, validate_layer_binding_draft
from .binding_completion import build_completion as build_head_completion
from .layer_binding import BLOCKERS
from .region_binding import _option

PROFILE='rigid-detail-completion-v4'
PREVIOUS={'rigid-or-limb-chain-v2','rigid-name-completion-v3'}


def build_completion(candidate, assisted, skeleton):
    result=build_head_completion(candidate,assisted,skeleton)
    bones={b['id']:b for b in skeleton['bones']}
    for source,row in zip(candidate['layers'],result['bindings']):
        if row['options'] or BLOCKERS.intersection(row['reason_codes']):continue
        name=' '.join(unicodedata.normalize('NFKC',source['name']).lower().split())
        match=re.fullmatch(r'(footwear|shoes?)(?:-([lr]))?',name)
        if not match:continue
        # Never reinterpret an explicitly different semantic as footwear.
        if source.get('semantic') not in (None,'body.foot','wear.shoe'):continue
        if any(key not in bones for key in ('foot_l','foot_r')):raise ValueError('binding_foot_topology_missing')
        options=[dict(id='rigid:'+key,mode='rigid',bone_ids=[key],setup_local=_option(bones[key],row['bbox'])['setup_local'])
                 for key in ('foot_l','foot_r')]
        side=match[2]
        row.update(options=options,suggested_option_id='rigid:foot_'+side if side else None,status='needs_review',
                   reason_codes=['footwear_name_candidate','character_side_requires_review','foot_attachment_extent_requires_review'])
    result['profile']=PROFILE
    return result


def validate_completion(candidate,assisted,skeleton,document):
    expected=build_completion(candidate,assisted,skeleton)
    if canonical_sha256(document)!=canonical_sha256(expected):raise ValueError('binding_completion_mismatch')
    return deepcopy(expected)


def inherit_unchanged(base,old_draft,completed):
    validate_layer_binding_draft(base,old_draft)
    if base['profile'] not in PREVIOUS or completed['profile']!=PROFILE \
            or any(base[k]!=completed[k] for k in ('candidate_sha256','source_skeleton_sha256')) \
            or [r['layer_id'] for r in base['bindings']]!=[r['layer_id'] for r in completed['bindings']]:
        raise ValueError('binding_completion_source_mismatch')
    draft=build_layer_binding_draft(completed)
    for old,new,record,target in zip(base['bindings'],completed['bindings'],old_draft['records'],draft['records']):
        # Structural/semantic review and exclusions remain user decisions even
        # when new options become available. A selected option must be unchanged.
        if record['action']=='bind':
            selected=next(o for o in old['options'] if o['id']==record['option_id'])
            if selected not in new['options']:raise ValueError('binding_completion_changed_reviewed_layer')
        target.update(deepcopy(record))
    return validate_layer_binding_draft(completed,draft)
