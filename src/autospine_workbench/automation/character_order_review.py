"""Append-only, exact-source slot precedence decisions for whole-character builds."""
import json

from ..manifest_artifacts import require_safe_token
from ..resolved_project import canonical_sha256
from ..targets.character43.order_candidate import generate, stable_order
from .pipeline_run import PipelineRunError
from .storage_io import directory, publish_document, read_document

SCHEMA = 'autospine.character-order-review/v1'
OPTIONS = ('motion_choice_id', 'residual_texture_profile', 'skirt_profile')


def overview(manager, project):
    require_safe_token(project, 'project')
    root = manager.root / 'order-decisions' / project
    previous = None; current = None
    if root.exists():
        directory(root)
        for revision, path in enumerate(sorted(root.glob('*.json'))):
            doc = read_document(path)
            valid = (set(doc) == {'schema', 'project_id', 'revision', 'previous_sha256',
                     'source_bundle_sha256', 'constraints', 'build_options', 'authority',
                     'production_authorized', 'decision_source', 'reversible'}
                     and path.name == f'{revision:06d}.json' and doc['schema'] == SCHEMA
                     and doc['project_id'] == project and type(doc['revision']) is int and doc['revision'] == revision
                     and doc['previous_sha256'] == previous and doc['authority'] == 'none'
                     and doc['production_authorized'] is False and doc['reversible'] is True
                     and doc['decision_source'] == 'human_confirmation'
                     and type(doc['constraints']) is list and type(doc['build_options']) is dict
                     and not set(doc['build_options']) - set(OPTIONS)
                     and all(type(v) is str for v in doc['build_options'].values()))
            if valid and doc['constraints']:
                digest = doc['source_bundle_sha256']
                valid = type(digest) is str and len(digest) == 64 and all(c in '0123456789abcdef' for c in digest)
                try:
                    pairs = doc['constraints']
                    names = sorted({v for row in pairs for v in row})
                    _, edges = stable_order(names, pairs)
                    valid = valid and pairs == [list(e) for e in edges]
                except (TypeError, ValueError): valid = False
            elif valid:
                valid = doc['source_bundle_sha256'] is None and not doc['build_options']
            if not valid: raise PipelineRunError('character_order_history_invalid')
            previous = canonical_sha256(doc); current = doc
    return dict(project_id=project, authority='none', head_sha256=previous,
                active=bool(current and current['constraints']), review=current)


def save(manager, project, body):
    keys = {'action', 'expected_head_sha256'}
    if body.get('action') == 'replace': keys |= {'job_id', 'expected_artifact_sha256', 'constraints'}
    elif body.get('action') != 'revoke': raise PipelineRunError('character_order_request_invalid')
    if set(body) != keys: raise PipelineRunError('character_order_request_invalid')
    with manager._lock:
        manager.projects.get_project(project)
        state = overview(manager, project)
        if state['head_sha256'] != body['expected_head_sha256']:
            raise PipelineRunError('character_order_review_conflict')
        digest = None; constraints = []; options = {}
        if body['action'] == 'replace':
            job = manager.get(project, body['job_id'])
            if job['status'] != 'needs_review' or job.get('artifact_sha256') != body['expected_artifact_sha256']:
                raise PipelineRunError('character_order_review_conflict')
            files = manager.verified_files(project, body['job_id'])
            digest = job['artifact_sha256']
            # Replacing an existing order always starts from its original pre-order candidate.
            if 'order-candidate.json' in files:
                digest = json.loads(files['order-candidate.json'])['source_bundle_sha256']
                files = manager.application.store.read(digest)
            _, report = generate(files, body['constraints'])
            if report['source_bundle_sha256'] != digest:
                raise PipelineRunError('character_order_source_changed')
            constraints = report['constraints']
            request = read_document(manager._path(body['job_id']) / 'request.json')
            options = {k: request[k] for k in OPTIONS if k in request}
        elif not state['active']: return state
        doc = dict(schema=SCHEMA, project_id=project,
                   revision=state['review']['revision'] + 1 if state['review'] else 0,
                   previous_sha256=state['head_sha256'], source_bundle_sha256=digest,
                   constraints=constraints, build_options=options, authority='none',
                   production_authorized=False, decision_source='human_confirmation', reversible=True)
        root = directory(manager.root / 'order-decisions' / project, create=True)
        if not publish_document(root / f'{doc["revision"]:06d}.json', doc, staging=root / 'staging'):
            raise PipelineRunError('character_order_review_conflict')
        return overview(manager, project)


def apply_saved(manager, request, result):
    state = overview(manager, request['project_id'])
    if state['head_sha256'] != request.get('order_decisions_sha256'):
        raise PipelineRunError('character_order_decisions_changed')
    if not state['active']: return result
    if state['review']['source_bundle_sha256'] != result['artifact_sha256']:
        raise PipelineRunError('character_order_source_changed')
    store = manager.application.store
    files, report = generate(store.read(result['artifact_sha256']), state['review']['constraints'])
    return dict(result, artifact_sha256=store.publish(files), manifest=json.loads(files['character-manifest.json']),
                order_review=dict(review_sha256=state['head_sha256'], constraints=report['constraints'], authority='none'))
