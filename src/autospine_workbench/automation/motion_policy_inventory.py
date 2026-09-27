"""Independent policy variants; never a view recommendation or baseline replacement."""
from ..resolved_project import canonical_sha256
from .pipeline_run import PipelineRunError
from .storage_io import read_document
from .motion_target_comparison import signature
from .motion_stage_review import inspect as stage_review

POLICIES = ('contact_correction', 'runtime_reference_profile', 'inferred_contact_profile',
            'depth_review_profile', 'torso_projection_profile', 'local_depth_profile',
            'pose_profile', 'moving_ankle_profile')


def family(value):
    return {k: v for k, v in value.items() if k not in POLICIES}


def inspect(manager, job_id):
    request = read_document(manager.folder(job_id) / 'request.json')
    if request.get('kind') != 'adapt':
        raise PipelineRunError('motion_target_comparison_requires_target')
    original = signature(manager, request)
    identity = family(original)
    matches = []
    for path in sorted(manager.root.glob('motion-*/request.json')):
        other = read_document(path)
        if other.get('kind') != 'adapt' or any(other.get(k) != request.get(k)
                for k in ('project_id', 'character_job_id', 'character_sha256', 'clip')):
            continue
        candidate = signature(manager, other)
        if family(candidate) == identity and candidate != original:
            matches.append((other, candidate))
    rows = []
    for other, candidate in matches[:24]:
        value = manager.get(other['job_id'])
        row = dict(job_id=other['job_id'], source_job_id=other['source_job_id'],
                   status=value['status'], projection=other.get('projection'),
                   view=manager.get(other['source_job_id'])['view'],
                   policy_changes={k: dict(baseline=original.get(k), candidate=candidate.get(k))
                                   for k in POLICIES if original.get(k) != candidate.get(k)})
        if value['status'] == 'succeeded':
            review = stage_review(manager, other['job_id'])
            row.update(artifact_sha256=review['artifact_sha256'], evidence_sha256=review['evidence_sha256'])
        rows.append(row)
    result = dict(profile='motion-policy-variant-inventory-v1', source_job_id=job_id,
                  identity=identity, rows=rows, matching_candidates=len(matches),
                  complete=len(matches) <= 24, authority='none', recommended_job_id=None,
                  scope='independent_policy_variants_not_comparable_view_recommendations')
    result['comparison_sha256'] = canonical_sha256(result)
    return result
