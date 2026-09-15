"""Explicit whole-character visual feedback bound to an exact rendered candidate."""
from .storage_io import directory, publish_document, read_document
from .pipeline_run import PipelineRunError
from ..resolved_project import canonical_sha256
from .character_review_timing import valid as valid_timing

SCHEMA='autospine.character-visual-review/v1'
ASPECTS={'setup','draw_order','connections','motion'}
VERDICTS={'acceptable','needs_changes','not_reviewed'}


def context(manager,project,job):
    reader=getattr(manager,'review_context',None)
    if callable(reader):
        result,_,_=reader(project,job)
        return result
    result=manager.get(project,job)
    if result['status']!='needs_review': raise PipelineRunError('pipeline_preview_not_ready')
    # Validate the candidate inventory and the actual report, not just a displayed job ID.
    manager.verified_files(project,job)
    manager.review_file(project,job,['report.json'])
    return result


def history(manager,job):
    root=manager._path(job)/'visual-review'
    if not root.exists(): return []
    directory(root)
    entries=[];previous=None
    for path in sorted(root.glob('*.json')):
        doc=read_document(path);digest=canonical_sha256(doc)
        if (path.name!=f'{len(entries):06d}.json' or doc.get('schema')!=SCHEMA
                or doc.get('previous_sha256')!=previous or doc.get('revision')!=len(entries)):
            raise PipelineRunError('character_review_history_invalid')
        entries.append((digest,doc));previous=digest
    return entries


def overview(manager,project,job):
    result=context(manager,project,job);entries=history(manager,job)
    current=entries[-1] if entries else None
    if current and (current[1]['project_id']!=project or current[1]['job_id']!=job
                    or current[1]['artifact_sha256']!=result['artifact_sha256']
                    or current[1]['runtime_sha256']!=canonical_sha256(result['runtime'])):
        raise PipelineRunError('character_review_source_mismatch')
    return dict(project_id=project,job_id=job,authority='none',artifact_sha256=result['artifact_sha256'],
                review_sha256=current[0] if current else None,review=current[1] if current else None)


def save(manager,project,job,body):
    keys={'expected_artifact_sha256','expected_review_sha256','aspects','notes'}
    if (set(body) not in (keys,keys|{'timing'}) or ('timing' in body and not valid_timing(body['timing']))
            or type(body['aspects']) is not dict or set(body['aspects'])!=ASPECTS
            or any(type(v) is not str or v not in VERDICTS for v in body['aspects'].values())
            or type(body['notes']) is not str or len(body['notes'])>2000):
        raise PipelineRunError('character_review_invalid')
    with manager._lock:
        current=overview(manager,project,job)
        if body['expected_artifact_sha256']!=current['artifact_sha256'] or body['expected_review_sha256']!=current['review_sha256']:
            raise PipelineRunError('character_review_conflict')
        result=manager.get(project,job)
        doc=dict(schema=SCHEMA,project_id=project,job_id=job,artifact_sha256=current['artifact_sha256'],
                 runtime_sha256=canonical_sha256(result['runtime']),previous_sha256=current['review_sha256'],
                 revision=0 if current['review'] is None else current['review']['revision']+1,
                 decision_source='human_review',authority='none',production_authorized=False,
                 aspects=body['aspects'],notes=body['notes'])
        timing=body.get('timing',(current['review'] or {}).get('timing'))
        if timing is not None:
            old=(current['review'] or {}).get('timing')
            if old and timing['seconds']<old['seconds']:
                raise PipelineRunError('character_review_timing_regression')
            doc['timing']=timing
        root=directory(manager._path(job)/'visual-review',create=True)
        if not publish_document(root/f"{doc['revision']:06d}.json",doc,staging=root/'staging'):
            raise PipelineRunError('character_review_conflict')
        return overview(manager,project,job)
