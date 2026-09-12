"""Append-only, exact-source region exclusions with explicit revocation."""
from hashlib import sha256
import json
from ..manifest_artifacts import require_safe_token
from ..resolved_project import canonical_sha256
from ..targets.character43.region_exclusion import apply
from .storage_io import directory, publish_document, read_document
from .pipeline_run import PipelineRunError
from .character_region_source import resolve


def history(manager, project):
    require_safe_token(project, 'project')
    root = manager.root/'region-decisions'/project
    if not root.exists(): return []
    directory(root); rows = []; previous = None
    for path in sorted(root.glob('*.json')):
        doc = read_document(path)
        if path.name != f'{len(rows):06d}.json' or doc.get('previous_sha256') != previous \
                or doc.get('project_id') != project or doc.get('schema') != 'autospine.character-region-history/v1':
            raise PipelineRunError('character_region_history_invalid')
        previous = canonical_sha256(doc); rows.append((previous, doc))
    return rows


def overview(manager, project):
    entries = history(manager, project); active = {}
    for digest, doc in entries:
        if doc['action'] == 'exclude': active[digest] = doc['decision']
        elif doc['action'] == 'revoke' and doc['decision_sha256'] in active:
            del active[doc['decision_sha256']]
        else: raise PipelineRunError('character_region_history_invalid')
    return dict(project_id=project, authority='none', head_sha256=entries[-1][0] if entries else None,
                active=[dict(decision_sha256=k, **v) for k, v in active.items()])


def save(manager, project, body):
    if body.get('action') not in ('exclude', 'revoke'):
        raise PipelineRunError('character_region_request_invalid')
    expected = {'action', 'expected_head_sha256'} | ({'job_id', 'expected_artifact_sha256', 'layer_id', 'region_id'}
                if body['action'] == 'exclude' else {'decision_sha256'})
    if set(body) != expected: raise PipelineRunError('character_region_request_invalid')
    with manager._lock:
        manager.projects.get_project(project)
        current = overview(manager, project)
        if body['expected_head_sha256'] != current['head_sha256']:
            raise PipelineRunError('character_region_review_conflict')
        doc = dict(schema='autospine.character-region-history/v1', project_id=project,
                   previous_sha256=current['head_sha256'], action=body['action'], authority='none')
        if body['action'] == 'revoke':
            if body['decision_sha256'] not in {d['decision_sha256'] for d in current['active']}:
                raise PipelineRunError('character_region_review_conflict')
            doc['decision_sha256'] = body['decision_sha256']
        else:
            job = manager.get(project, body['job_id'])
            if job['status'] != 'needs_review' or job['artifact_sha256'] != body['expected_artifact_sha256']:
                raise PipelineRunError('character_region_review_conflict')
            manager.download(project, body['job_id'])
            files = manager.application.store.read(job['artifact_sha256'])
            manifest = json.loads(files['character-manifest.json'])
            skeleton = json.loads(files['skeleton.json'])
            region = body['region_id']; item = skeleton['skins'][0]['attachments'][region][region]
            decision = dict(schema='autospine.region-exclusion/v1', decision_source='human_confirmation',
                            source_bundle_sha256=job['artifact_sha256'], manifest_sha256=canonical_sha256(manifest),
                            layer_id=body['layer_id'], region_id=region,
                            image_sha256=sha256(files['images/'+item.get('path', region)+'.png']).hexdigest(), reversible=True)
            apply(files, decision)  # Validate concrete scope before recording authority.
            try:
                base_digest, base = resolve(manager.application.store, job['artifact_sha256'], files)
                if base_digest != job['artifact_sha256']:
                    decision.update(reviewed_bundle_sha256=job['artifact_sha256'],
                                    reviewed_manifest_sha256=decision['manifest_sha256'],
                                    source_bundle_sha256=base_digest,
                                    manifest_sha256=sha256(base['character-manifest.json']).hexdigest())
                    apply(base, decision)
            except (ValueError, KeyError, IndexError):
                raise PipelineRunError('character_region_source_changed') from None
            doc['decision'] = decision
        root = directory(manager.root/'region-decisions'/project, create=True)
        revision = len(history(manager, project))
        if not publish_document(root/f'{revision:06d}.json', doc, staging=root/'staging'):
            raise PipelineRunError('character_region_review_conflict')
        return overview(manager, project)


def apply_saved(manager, project, result, expected_head):
    current = overview(manager, project)
    if current['head_sha256'] != expected_head:
        raise PipelineRunError('character_region_decisions_changed')
    if not current['active']: return result
    files = manager.application.store.read(result['artifact_sha256'])
    for row in current['active']:
        decision = {k: v for k, v in row.items() if k != 'decision_sha256'}
        try: files = apply(files, decision)
        except (ValueError, KeyError): raise PipelineRunError('character_region_source_changed') from None
    digest = manager.application.store.publish(files)
    return dict(artifact_sha256=digest, manifest=json.loads(files['character-manifest.json']))
