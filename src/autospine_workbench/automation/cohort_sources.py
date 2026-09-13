"""Verify audit declarations against local audit and PSD bytes without edits."""
from hashlib import file_digest, sha256
import json
from pathlib import Path
import re


def inside(root, relative):
    path = (root / relative).resolve(strict=True)
    path.relative_to(root.resolve(strict=True))
    return path


def verify(workspace, manifest, project_documents):
    workspace = Path(workspace)
    files = {}
    for character in manifest['characters']:
        if character['dataset_split'] not in ('development', 'visible', 'holdout'):
            continue
        for item in character['psd_candidates']:
            source = item['source']; key = source['sha256']
            try:
                path = inside(workspace, source['path'])
                with path.open('rb') as stream:
                    digest = file_digest(stream, 'sha256').hexdigest()
                files[key] = dict(path=source['path'], actual_sha256=digest,
                                  status='verified' if digest == key else 'source_bytes_changed')
            except (OSError, ValueError):
                files[key] = dict(path=source['path'], status='source_unavailable')
    observations = {}
    for project_id, document in project_documents.items():
        result = dict(status='audit_source_unverified')
        observations[project_id] = result
        source = document.get('source', {})
        if document.get('id') != project_id:
            result['status'] = 'project_identity_mismatch'
            continue
        audit_id = source.get('audit_id', '')
        if not re.fullmatch(r'[A-Za-z0-9_-]+', audit_id):
            continue
        try:
            raw = inside(workspace / 'tmp/psd_audit/results', audit_id + '/audit.json').read_bytes()
            digest = sha256(raw).hexdigest()
            audit = json.loads(raw)
            declared = source.get('sha256')
            if digest != source.get('audit_sha256') or audit.get('sha256') != declared:
                result['status'] = 'audit_identity_changed'
                continue
            if files.get(declared, {}).get('status') != 'verified':
                result['status'] = 'psd_identity_unverified'
                continue
            result.update(status='verified', source_sha256=declared, audit_sha256=digest,
                          project_document_sha256=sha256(json.dumps(document, sort_keys=True).encode()).hexdigest())
        except (OSError, ValueError):
            result['status'] = 'audit_unavailable'
    return dict(schema='autospine.cohort-source-check/v1', authority='none', files=files, projects=observations)
