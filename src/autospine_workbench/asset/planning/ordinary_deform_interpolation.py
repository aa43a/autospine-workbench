"""Dense sampled interpolation evidence kept separate from discrete D1 identity."""
from .ordinary_sleeve_deform_validation import validate as validate_deform
from .ordinary_deform_sampling import sample
from ...resolved_project import canonical_sha256

SCHEMA = 'autospine.ordinary-deform-interpolation/v1'
PROFILE = 'ordinary-deform-quarter-tick513-v1'


def build(deform, *, repair, source, draft, skeleton):
    validate_deform(deform, repair=repair, source=source, draft=draft, skeleton=skeleton)
    bones = {b['id']: b for b in skeleton['bones']}
    records = []
    for original in deform['records']:
        row = dict(layer_id=original['layer_id'], component_id=original['component_id'],
                   status='blocked', reason_codes=[], tracks=[])
        records.append(row)
        if not original['tracks']:
            row['reason_codes'] = original['reason_codes'][:]
            continue
        mesh = dict(vertices_xy=original['setup_vertices'], triangles=original['triangles'],
                    weights=original['weights'], bone_ids=original['bone_ids'])
        chain = [bones[b] for b in original['bone_ids']]
        for track in original['tracks']:
            row['tracks'].append(dict(bone_id=track['bone_id'], **sample(mesh, chain, track)))
        reasons = []
        if original['status'] == 'blocked': reasons.append('source_region_blocked')
        if any(t['failed_samples'] for t in row['tracks']): reasons.append('sampled_interpolation_geometry_failure')
        if any(t['new_failed_between_keys'] for t in row['tracks']): reasons.append('interpolation_introduces_failure')
        if any(t['setup_error'] > 1e-7 for t in row['tracks']): reasons.append('setup_reconstruction_failure')
        if any(not t['loop_exact'] for t in row['tracks']): reasons.append('loop_failure')
        row.update(status='blocked' if reasons else 'sampled_interpolation_passed',
                   reason_codes=reasons or ['temporal_quality_review_required', 'target_interpolation_required', 'runtime_required'])
    return dict(schema=SCHEMA, profile=PROFILE, project_id=deform['project_id'],
                deform_sha256=canonical_sha256(deform), repair_sha256=canonical_sha256(repair),
                source_sha256=canonical_sha256(source), draft_sha256=canonical_sha256(draft),
                skeleton_sha256=canonical_sha256(skeleton), records=records,
                continuous_time_proven=False, temporal_quality_status='needs_review',
                target_interpolation_status='not_evaluated', runtime_status='not_evaluated',
                authority='none', production_authorized=False)


def validate(document, *, deform, repair, source, draft, skeleton):
    if (not isinstance(document, dict) or document.get('schema') != SCHEMA
            or document.get('profile') != PROFILE):
        raise ValueError('ordinary_interpolation_contract_invalid')
    expected = build(deform, repair=repair, source=source, draft=draft, skeleton=skeleton)
    if canonical_sha256(expected) != canonical_sha256(document):
        raise ValueError('ordinary_interpolation_replay_mismatch')
    return document
