"""Human spot checks of exact automatic bindings; never inferred from acceptance."""
from copy import deepcopy
import re

from ..resolved_project import canonical_sha256
from .character_visual_review import context
from .pipeline_run import PipelineRunError
from .storage_io import directory, publish_document, read_document
from .character_review_timing import valid as valid_timing

SCHEMA = 'autospine.character-auto-binding-audit/v1'
SCHEMA_V2 = 'autospine.character-auto-binding-audit/v2'
VERDICTS = {'correct', 'incorrect', 'unobservable', 'not_reviewed'}
TIMING_SCOPE = 'automatic_binding_audit_session'
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


def checked_reviews(job, value):
    if not value or value.get('authority') != 'none': return None
    expected = dict(project_id=job.get('project_id'), job_id=job.get('job_id'),
                    artifact_sha256=job.get('artifact_sha256'))
    if any(value.get(k) != v for k, v in expected.items()): return None
    doc = value.get('review')
    if not doc: return None
    if 'timing' in doc and not valid_timing(doc['timing'], TIMING_SCOPE): return None
    expected.update(inventory_sha256=canonical_sha256(inventory(job)),
                    decision_source='human_audit', authority='none', production_authorized=False)
    resolutions = doc.get('exception_resolutions', [])
    if (doc.get('schema') not in (SCHEMA, SCHEMA_V2)
            or (doc.get('schema') == SCHEMA and 'exception_resolutions' in doc)
            or (doc.get('schema') == SCHEMA_V2 and 'exception_resolutions' not in doc)
            or type(resolutions) is not list or len(resolutions) > 1024
            or any(type(r) is not str or not re.fullmatch('[a-f0-9]{64}', r) for r in resolutions)
            or resolutions != sorted(set(resolutions))): return None
    if (value.get('review_sha256') != canonical_sha256(doc)
            or any(doc.get(k) != v for k, v in expected.items())): return None
    reviews = doc.get('reviews'); allowed = {r['layer_id'] for r in inventory(job)}
    if (type(reviews) is not dict or not set(reviews) <= allowed
            or any(type(v) is not str or v not in VERDICTS for v in reviews.values())): return None
    return deepcopy(reviews)


def verified_reviews(job, value):
    return checked_reviews(job, value) or {}


def summary(job, value):
    from .character_audit_continuity import verified_exceptions
    from .character_audit_history_metrics import summarize as historical_summary
    rows = inventory(job); reviews = verified_reviews(job, value)
    counts = {v: sum(reviews.get(r['layer_id'], 'not_reviewed') == v for r in rows) for v in VERDICTS}
    assessed = counts['correct'] + counts['incorrect']
    carried = {r['layer_id'] for r in verified_exceptions(job, value)}
    return dict(eligible_bindings=len(rows), assessed_bindings=assessed, **counts,
                historical_audit=historical_summary(job, value),
                carried_exception_layers=len(carried),
                default_unreviewed_bindings=sum(reviews.get(r['layer_id'], 'not_reviewed') == 'not_reviewed'
                    and r['layer_id'] not in carried for r in rows),
                audit_session_minutes=(value['review']['timing']['seconds']/60
                    if checked_reviews(job, value) is not None and (value.get('review') or {}).get('timing') else None),
                sampled_error_rate=counts['incorrect']/assessed if assessed else None,
                sampling_scope='human_selected_current_bindings_not_population_accuracy')


def read_history(root, result):
    rows = inventory(result)
    value = dict(project_id=result['project_id'], job_id=result['job_id'], artifact_sha256=result['artifact_sha256'],
                 authority='none', inventory=rows, review_sha256=None, review=None)
    entries = []
    if root.exists():
        directory(root)
        for revision, path in enumerate(sorted(root.glob('*.json'))):
            doc = read_document(path); candidate = dict(value, review=doc, review_sha256=canonical_sha256(doc))
            extras = {'timing', 'exception_resolutions'} if doc.get('schema') == SCHEMA_V2 else {'timing'}
            if (not FIELDS <= set(doc) or set(doc)-FIELDS-extras or path.name != f'{revision:06d}.json'
                    or ('timing' in doc and not valid_timing(doc['timing'], TIMING_SCOPE))
                    or ((value.get('review') or {}).get('timing') and
                        (not doc.get('timing') or doc['timing']['seconds'] < value['review']['timing']['seconds']))
                    or type(doc.get('revision')) is not int or doc.get('revision') != revision
                    or doc.get('previous_sha256') != value['review_sha256']
                    or type(doc.get('reviews')) is not dict or len(doc['reviews']) > 128
                    or checked_reviews(result, candidate) != doc['reviews']
                    or not set((value.get('review') or {}).get('exception_resolutions', [])) <= set(doc.get('exception_resolutions', []))
                    or doc.get('schema') not in (SCHEMA, SCHEMA_V2) or doc.get('inventory_sha256') != canonical_sha256(rows)
                    or any(doc.get(k) != value[k] for k in ('project_id', 'job_id', 'artifact_sha256'))
                    or doc.get('decision_source') != 'human_audit' or doc.get('authority') != 'none'
                    or doc.get('production_authorized') is not False):
                raise PipelineRunError('character_auto_audit_history_invalid')
            value = candidate
            entries.append(candidate)
    return value, entries


def overview(manager, project, job):
    result = context(manager, project, job)
    value, _ = read_history(manager._path(job)/'auto-binding-audit', result)
    from .character_audit_continuity import collect
    value['exception_continuity'] = collect(manager, result)
    value['exception_sha256'] = canonical_sha256(value['exception_continuity'])
    value['metrics'] = summary(result, value)
    return value


def save(manager, project, job, body):
    keys = {'expected_artifact_sha256', 'expected_review_sha256', 'reviews'}
    if (not keys <= set(body) or set(body)-keys-{'timing', 'expected_exception_sha256'}
            or ('timing' in body and not valid_timing(body['timing'], TIMING_SCOPE))
            or type(body['reviews']) is not dict or (not body['reviews'] and 'timing' not in body) or len(body['reviews']) > 128
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
        continuity = current['exception_continuity']
        if (continuity['exceptions'] or 'expected_exception_sha256' in body) and body.get('expected_exception_sha256') != canonical_sha256(continuity):
            raise PipelineRunError('character_review_conflict')
        resolutions = set((old or {}).get('exception_resolutions', []))
        for issue in continuity['exceptions']:
            if body['reviews'].get(issue['layer_id']) in {'correct', 'not_reviewed'}:
                resolutions.add(issue['exception_id'])
        if len(resolutions) > 1024: raise PipelineRunError('character_auto_audit_invalid')
        timing = body.get('timing', (old or {}).get('timing'))
        if old and old.get('timing') and timing['seconds'] < old['timing']['seconds']:
            raise PipelineRunError('character_review_timing_regression')
        if old and old['reviews'] == reviews and old.get('timing') == timing and sorted(resolutions) == old.get('exception_resolutions', []): return current
        doc = dict(schema=SCHEMA_V2 if resolutions else SCHEMA, project_id=project, job_id=job, artifact_sha256=current['artifact_sha256'],
                   inventory_sha256=canonical_sha256(current['inventory']), reviews=reviews,
                   revision=old['revision']+1 if old else 0, previous_sha256=current['review_sha256'],
                   decision_source='human_audit', authority='none', production_authorized=False)
        if timing is not None: doc['timing'] = timing
        if resolutions: doc['exception_resolutions'] = sorted(resolutions)
        root = directory(manager._path(job)/'auto-binding-audit', create=True)
        if not publish_document(root/f'{doc["revision"]:06d}.json', doc, staging=root/'staging'):
            raise PipelineRunError('character_review_conflict')
        return overview(manager, project, job)
