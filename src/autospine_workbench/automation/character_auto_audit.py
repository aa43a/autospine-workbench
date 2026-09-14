"""Human spot checks of exact automatic bindings; never inferred from acceptance."""
from copy import deepcopy
import re

from ..resolved_project import canonical_sha256
from .character_visual_review import context
from .pipeline_run import PipelineRunError
from .storage_io import directory, publish_document, read_document

SCHEMA = 'autospine.character-auto-binding-audit/v1'
VERDICTS = {'correct', 'incorrect', 'unobservable', 'not_reviewed'}
FIELDS = {'schema', 'project_id', 'job_id', 'artifact_sha256', 'inventory_sha256', 'reviews',
          'revision', 'previous_sha256', 'decision_source', 'authority', 'production_authorized'}


def inventory(job):
    rows = []
    for layer in job.get('layers', []):
        decision = layer.get('binding_decision', {})
        if (decision.get('decision_source') == 'policy_auto' and decision.get('evidence_current') is True
                and decision.get('action') == 'bind' and type(decision.get('decision_sha256')) is str
                and re.fullmatch('[a-f0-9]{64}', decision['decision_sha256'])):
            rows.append(dict(layer_id=layer['layer_id'], name=layer['name'],
                             decision_sha256=decision['decision_sha256'], option_id=decision['option_id'],
                             policy_id=decision['policy_id']))
    return sorted(rows, key=lambda row: row['layer_id'])


def verified_reviews(job, value):
    if not value or value.get('authority') != 'none': return {}
    expected = dict(project_id=job.get('project_id'), job_id=job.get('job_id'),
                    artifact_sha256=job.get('artifact_sha256'))
    if any(value.get(k) != v for k, v in expected.items()): return {}
    doc = value.get('review')
    if not doc: return {}
    expected.update(schema=SCHEMA, inventory_sha256=canonical_sha256(inventory(job)),
                    decision_source='human_audit', authority='none', production_authorized=False)
    if (value.get('review_sha256') != canonical_sha256(doc)
            or any(doc.get(k) != v for k, v in expected.items())): return {}
    reviews = doc.get('reviews'); allowed = {r['layer_id'] for r in inventory(job)}
    if (type(reviews) is not dict or not set(reviews) <= allowed
            or any(type(v) is not str or v not in VERDICTS for v in reviews.values())): return {}
    return deepcopy(reviews)


def summary(job, value):
    rows = inventory(job); reviews = verified_reviews(job, value)
    counts = {v: sum(reviews.get(r['layer_id'], 'not_reviewed') == v for r in rows) for v in VERDICTS}
    assessed = counts['correct'] + counts['incorrect']
    return dict(eligible_bindings=len(rows), assessed_bindings=assessed, **counts,
                sampled_error_rate=counts['incorrect']/assessed if assessed else None,
                sampling_scope='human_selected_current_bindings_not_population_accuracy')


def overview(manager, project, job):
    result = context(manager, project, job); rows = inventory(result)
    root = manager._path(job)/'auto-binding-audit'
    value = dict(project_id=project, job_id=job, artifact_sha256=result['artifact_sha256'],
                 authority='none', inventory=rows, review_sha256=None, review=None)
    if root.exists():
        directory(root)
        for revision, path in enumerate(sorted(root.glob('*.json'))):
            doc = read_document(path); candidate = dict(value, review=doc, review_sha256=canonical_sha256(doc))
            if (set(doc) != FIELDS or path.name != f'{revision:06d}.json'
                    or type(doc.get('revision')) is not int or doc.get('revision') != revision
                    or doc.get('previous_sha256') != value['review_sha256']
                    or type(doc.get('reviews')) is not dict or len(doc['reviews']) > 128
                    or verified_reviews(result, candidate) != doc['reviews']
                    or doc.get('schema') != SCHEMA or doc.get('inventory_sha256') != canonical_sha256(rows)
                    or any(doc.get(k) != value[k] for k in ('project_id', 'job_id', 'artifact_sha256'))
                    or doc.get('decision_source') != 'human_audit' or doc.get('authority') != 'none'
                    or doc.get('production_authorized') is not False):
                raise PipelineRunError('character_auto_audit_history_invalid')
            value = candidate
    value['metrics'] = summary(result, value)
    return value


def save(manager, project, job, body):
    if (set(body) != {'expected_artifact_sha256', 'expected_review_sha256', 'reviews'}
            or type(body['reviews']) is not dict or not body['reviews'] or len(body['reviews']) > 128
            or any(type(v) is not str or v not in VERDICTS for v in body['reviews'].values())):
        raise PipelineRunError('character_auto_audit_invalid')
    with manager._lock:
        current = overview(manager, project, job)
        if (body['expected_artifact_sha256'] != current['artifact_sha256']
                or body['expected_review_sha256'] != current['review_sha256']):
            raise PipelineRunError('character_review_conflict')
        if not set(body['reviews']) <= {r['layer_id'] for r in current['inventory']}:
            raise PipelineRunError('character_auto_audit_scope_invalid')
        old = current['review']; reviews = dict(old['reviews'] if old else {}, **body['reviews'])
        if old and old['reviews'] == reviews: return current
        doc = dict(schema=SCHEMA, project_id=project, job_id=job, artifact_sha256=current['artifact_sha256'],
                   inventory_sha256=canonical_sha256(current['inventory']), reviews=reviews,
                   revision=old['revision']+1 if old else 0, previous_sha256=current['review_sha256'],
                   decision_source='human_audit', authority='none', production_authorized=False)
        root = directory(manager._path(job)/'auto-binding-audit', create=True)
        if not publish_document(root/f'{doc["revision"]:06d}.json', doc, staging=root/'staging'):
            raise PipelineRunError('character_review_conflict')
        return overview(manager, project, job)
