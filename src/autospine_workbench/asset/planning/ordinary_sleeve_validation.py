"""Replay ordinary-sleeve FK diagnostics before target compilation."""
import math
import re
from .ordinary_sleeve import SCHEMA, PROFILE, MOTIONS, track, _validate_mesh, build
from .sleeve_helpers import frames
from ..joints.mesh_weights import _deform
from ...resolved_project import canonical_sha256

_TOP = {'schema', 'profile', 'project_id', 'source_sha256', 'draft_sha256',
        'skeleton_sha256', 'records', 'authority', 'production_authorized',
        'runtime_status', 'corrective_status'}
_ROW = {'layer_id', 'component_id', 'status', 'reason_codes'}
_FULL = _ROW | {'bone_ids', 'setup_vertices', 'triangles', 'weights', 'tracks',
                'setup_error', 'weight_sum_error', 'motion_envelope'}
_UNAVAILABLE = {'ordinary_sleeve_region_unavailable', 'ordinary_sleeve_drape_branch_required',
                'ordinary_sleeve_roles_required'}


def validate(document, skeleton, *, source=None, draft=None):
    """Replay every FK/QA sample, optionally also verify exact source+label closure.

    Target callers without the label closure still get strict numeric replay;
    authority remains none. Admission of label completeness requires that closure.
    """
    def require(condition):
        if not condition: raise ValueError('ordinary_sleeve_document_invalid')

    require(type(document) is dict and set(document) == _TOP)
    require(document['schema'] == SCHEMA and document['profile'] == PROFILE
            and document['authority'] == 'none' and document['production_authorized'] is False
            and document['runtime_status'] == 'not_evaluated' and document['corrective_status'] == 'not_applied')
    require(type(document['project_id']) is str and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}', document['project_id']))
    for name in ('source_sha256', 'draft_sha256', 'skeleton_sha256'):
        require(type(document[name]) is str and re.fullmatch('[a-f0-9]{64}', document[name]))
    require(document['skeleton_sha256'] == canonical_sha256(skeleton))
    require(type(document['records']) is list)
    # Canonical encoding also rejects NaN/infinity in nested diagnostics.
    canonical_sha256(document)
    bones = {b['id']: b for b in skeleton['bones']}
    require(len(bones) == len(skeleton['bones']))
    seen = set()
    for row in document['records']:
        require(type(row) is dict and set(row) in (_ROW, _FULL))
        require(all(type(row[k]) is str and bool(row[k]) for k in ('layer_id', 'component_id')))
        key = row['layer_id'], row['component_id']; require(key not in seen); seen.add(key)
        reasons = row['reason_codes']
        require(type(reasons) is list and all(type(r) is str for r in reasons) and len(set(reasons)) == len(reasons))
        if set(row) == _ROW:
            require(row['status'] == 'blocked' and len(reasons) == 1 and reasons[0] in _UNAVAILABLE)
            continue
        ids = row['bone_ids']; require(type(ids) is list and len(ids) == 3)
        suffix = ids[0][-1] if type(ids[0]) is str and ids[0] else ''
        require(suffix in ('l', 'r') and ids == [f'{b}_{suffix}' for b in ('upperarm', 'forearm', 'hand')]
                and all(b in bones for b in ids))
        require(all(bones[ids[i]]['parent_id'] == ids[i-1] for i in (1, 2)))
        chain = [bones[b] for b in ids]
        mesh = dict(vertices_xy=row['setup_vertices'], triangles=row['triangles'], weights=row['weights'])
        _validate_mesh(mesh, chain)
        expected = [track(mesh, chain, name, amplitudes) for name, amplitudes in MOTIONS]
        # Exact replay enforces four unique names, two drivers, QA and sample inventories,
        # amplitudes, loop values, failure counts, and the absence of corrective keys.
        require(canonical_sha256(row['tracks']) == canonical_sha256(expected))
        setup = _deform(row['weights'], frames(chain, {}))
        error = max(math.dist(a, b) for a, b in zip(row['setup_vertices'], setup))
        sums = max(abs(sum(w['weight'] for w in entries)-1) for entries in row['weights'])
        require(all(type(row[k]) in (int, float) for k in ('setup_error', 'weight_sum_error')))
        require(row['setup_error'] == error and row['weight_sum_error'] == sums)
        expected_reasons = ['ownership_review_required'] if 'ownership_review_required' in reasons else []
        if error > 1e-7: expected_reasons.append('setup_reconstruction_failure')
        if sums > 1e-9: expected_reasons.append('weight_sum_failure')
        if any(t['loop_error'] > 1e-7 for t in expected): expected_reasons.append('loop_failure')
        failed = any(t['failed_ticks'] for t in expected)
        if failed: expected_reasons.append('motion_envelope_geometry_failure')
        require(row['status'] == ('blocked' if expected_reasons else 'candidate_requires_review'))
        require(reasons == (expected_reasons or ['runtime_and_alpha_contact_required']))
        require(canonical_sha256(row['motion_envelope']) == canonical_sha256(dict(
            geometry_pass=not failed, alpha_contact_status='not_evaluated',
            full_angle_volume_proven=False, combined_sampling='same_and_opposed_synchronized_sine')))
    if source is not None or draft is not None:
        require(source is not None and draft is not None)
        require(canonical_sha256(document) == canonical_sha256(build(source, draft, skeleton)))
    return document
