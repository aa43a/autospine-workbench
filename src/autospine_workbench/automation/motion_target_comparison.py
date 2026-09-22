"""Read-only comparison of existing exact-source character view candidates."""
from ..resolved_project import canonical_sha256
from .pipeline_run import PipelineRunError
from .storage_io import read_document
from .motion_stage_review import inspect as stage_review

PROFILE = 'verified-target-view-comparison-v2'
KEYS = ('project_id', 'character_job_id', 'character_sha256', 'clip',
        'contact_correction', 'runtime_reference_profile', 'inferred_contact_profile',
        'depth_review_profile', 'torso_projection_profile', 'local_depth_profile')


def signature(manager, request):
    source = manager.get(request['source_job_id'])
    return {**({'pose_profile':request['pose_profile']} if 'pose_profile' in request else {}),
            **{key: request.get(key) for key in KEYS},
            'source_sha256': source['source_sha256'], 'source_format': source['format'],
            'source_sampling': {key: source.get('result', {}).get(key)
                                for key in ('frame_count', 'fps', 'duration_seconds')}}


def recommend(rows, *, complete):
    if not complete:
        return None
    qualified = [r for r in rows if r.get('readiness') == 'stage_review'
                 and r.get('visual_decision') not in ('rejected', 'evidence_changed')]
    # Technical recommendation only; no automatic human acceptance or replacement.
    return min(qualified, key=lambda r: (r.get('visual_decision') != 'accepted',
                                        r['job_id']))['job_id'] if qualified else None


def inspect(manager, job_id):
    request = read_document(manager.folder(job_id) / 'request.json')
    if request.get('kind') != 'adapt':
        raise PipelineRunError('motion_target_comparison_requires_target')
    identity = signature(manager, request)
    matches = []
    for path in sorted(manager.root.glob('motion-*/request.json')):
        other = read_document(path)
        if other.get('kind') != 'adapt' or any(other.get(k) != request.get(k) for k in KEYS):
            continue
        if signature(manager, other) == identity:
            matches.append(other)
    # Bound expensive artifact verification, explicitly declining recommendations
    # when the inventory cannot be evaluated in full.
    complete = len(matches) <= 24
    rows = []
    for other in matches[:24]:
        candidate = other['job_id']
        value = manager.get(candidate)
        source = manager.get(other['source_job_id'])
        row = dict(job_id=candidate, status=value['status'], source_job_id=source['job_id'],
                   view=source['view'], projection=other.get('projection'))
        if value['status'] == 'succeeded':
            review = stage_review(manager, candidate)
            current = review['current']
            decision = (current['decision'] if review['current_applies'] else
                        'evidence_changed' if current else 'not_reviewed')
            row.update(artifact_sha256=review['artifact_sha256'],
                       evidence_sha256=review['evidence_sha256'], visual_decision=decision,
                       readiness=review['readiness']['status'], stages=review['readiness']['stages'])
        rows.append(row)
    report = dict(profile=PROFILE, source_job_id=job_id, identity=identity, rows=rows,
                  complete=complete, matching_candidates=len(matches),
                  recommended_job_id=recommend(rows, complete=complete), authority='none',
                  scope='existing_candidates_technical_recommendation_not_visual_acceptance')
    report['comparison_sha256'] = canonical_sha256(report)
    return report
