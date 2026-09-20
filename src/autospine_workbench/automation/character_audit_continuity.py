"""Carry unresolved human exceptions by exact automatic decision, never by recency."""
from copy import deepcopy
from pathlib import Path

from ..resolved_project import canonical_sha256
from .pipeline_run import PipelineRunError
from .storage_io import read_document

SCHEMA = 'autospine.character-audit-exception-continuity/v1'


def identity(row):
    return tuple(row[k] for k in ('layer_id', 'decision_sha256', 'option_id', 'policy_id'))


def derive(job, histories):
    from .character_auto_audit import inventory, checked_reviews
    targets = {identity(row) for row in inventory(job)}
    issues = {}; resolutions = []
    seen = set()
    for history in histories:
        source = history['job']; entries = history['entries']
        if source['project_id'] != job['project_id'] or source['job_id'] in seen:
            raise PipelineRunError('character_audit_continuity_invalid')
        seen.add(source['job_id'])
        rows = {r['layer_id']: r for r in inventory(source)}
        active = {}; previous = None; old_resolutions = set()
        for index, value in enumerate(entries):
            doc = value['review']; verdicts = checked_reviews(source, value)
            if (verdicts is None or verdicts != doc['reviews'] or doc['revision'] != index
                    or doc['previous_sha256'] != previous
                    or not old_resolutions <= set(doc.get('exception_resolutions', []))):
                raise PipelineRunError('character_audit_continuity_invalid')
            previous = value['review_sha256']
            old_resolutions = set(doc.get('exception_resolutions', []))
            for layer, row in rows.items():
                if verdicts.get(layer) != 'incorrect':
                    active.pop(layer, None)
                elif layer not in active:
                    issue = dict(layer_id=layer, binding_identity=list(identity(row)),
                                 source_job_id=source['job_id'], source_artifact_sha256=source['artifact_sha256'],
                                 source_review_sha256=value['review_sha256'])
                    issue['exception_id'] = canonical_sha256(issue)
                    active[layer] = issue
            # A resolution only affects issues with an identical binding on this audited job.
            for digest in doc.get('exception_resolutions', []):
                allowed = {identity(rows[k]) for k, verdict in verdicts.items()
                           if verdict in {'correct', 'not_reviewed'}}
                resolutions.append((digest, allowed))
        issues.update({v['exception_id']: v for v in active.values()})
    for digest, allowed in resolutions:
        if digest in issues and tuple(issues[digest]['binding_identity']) in allowed:
            del issues[digest]
    return sorted((v for v in issues.values() if tuple(v['binding_identity']) in targets
                   and v['source_job_id'] != job['job_id']), key=lambda v:v['exception_id'])


def collect(manager, job):
    from .character_auto_audit import read_history
    histories = []
    root = getattr(manager, 'root', None)
    if root is not None:
        for folder in sorted(Path(root).glob('job-*/auto-binding-audit')):
            result_path = folder.parent/'result.json'
            if not result_path.exists(): continue
            source = read_document(result_path)
            if source.get('project_id') != job['project_id']: continue
            if source.get('job_id') != folder.parent.name:
                raise PipelineRunError('character_audit_continuity_invalid')
            _, entries = read_history(folder, source)
            if entries:
                histories.append(dict(job={k:deepcopy(source[k]) for k in
                    ('project_id', 'job_id', 'artifact_sha256', 'layers')}, entries=entries))
    return dict(schema=SCHEMA, project_id=job['project_id'], job_id=job['job_id'],
                artifact_sha256=job['artifact_sha256'], authority='none',
                histories=histories, exceptions=derive(job, histories))


def verified_exceptions(job, value):
    proof = (value or {}).get('exception_continuity')
    if not proof: return []
    try:
        if (proof['schema'] != SCHEMA or proof['authority'] != 'none'
                or value.get('exception_sha256') != canonical_sha256(proof)
                or any(proof[k] != job[k] for k in ('project_id', 'job_id', 'artifact_sha256'))): return []
        expected = derive(job, proof['histories'])
        return expected if expected == proof['exceptions'] else []
    except (KeyError, TypeError, ValueError, RuntimeError):
        return []
