"""Append-only final-stage residual decisions, bound to an exact derived candidate."""
from hashlib import sha256
import json
import re
from ..resolved_project import canonical_sha256
from ..manifest_artifacts import require_safe_token
from ..targets.character43.final_region_exclusion import apply_batch
from .storage_io import directory, read_document, publish_document
from .pipeline_run import PipelineRunError

SCHEMA='autospine.character-final-regions/v1'


def _valid_scope(doc):
    decisions=doc.get('decisions'); options=doc.get('build_options')
    if type(decisions) is not list or len(decisions)>64 or type(options) is not dict:
        return False
    if set(options)-{'motion_choice_id','residual_texture_profile','skirt_profile'}:
        return False
    if any(type(value) is not str for value in options.values()): return False
    if not decisions: return doc.get('source_bundle_sha256') is None and not options
    keys={'schema','decision_source','source_bundle_sha256','manifest_sha256','layer_id','region_id','image_sha256','reversible'}
    seen=set()
    for decision in decisions:
        if type(decision) is not dict or set(decision)!=keys: return False
        if (decision['schema']!='autospine.region-exclusion/v1'
                or decision['decision_source']!='human_confirmation' or decision['reversible'] is not True
                or decision['source_bundle_sha256']!=doc.get('source_bundle_sha256')): return False
        for key in ('source_bundle_sha256','manifest_sha256','image_sha256'):
            if type(decision[key]) is not str or not re.fullmatch('[a-f0-9]{64}',decision[key]): return False
        if any(type(decision[k]) is not str or not decision[k] for k in ('layer_id','region_id')): return False
        identity=(decision['layer_id'],decision['region_id'])
        if identity in seen: return False
        seen.add(identity)
    return True


def overview(manager, project):
    require_safe_token(project,'project')
    root=manager.root/'final-region-decisions'/project
    entries=[]; previous=None
    if root.exists():
        directory(root)
        for path in sorted(root.glob('*.json')):
            doc=read_document(path)
            if (path.name!=f'{len(entries):06d}.json' or doc.get('schema')!=SCHEMA
                    or doc.get('project_id')!=project or doc.get('previous_sha256')!=previous
                    or doc.get('revision')!=len(entries) or doc.get('authority')!='none'
                    or doc.get('decision_source')!='human_confirmation'
                    or doc.get('production_authorized') is not False or not _valid_scope(doc)):
                raise PipelineRunError('character_final_history_invalid')
            previous=canonical_sha256(doc); entries.append(doc)
    current=entries[-1] if entries else None
    return dict(project_id=project,authority='none',head_sha256=previous,
                review=current,active=bool(current and current['decisions']))


def save(manager,project,body):
    keys={'expected_head_sha256','action'}
    if body.get('action')=='replace': keys|={'job_id','expected_artifact_sha256','regions'}
    elif body.get('action')!='revoke': raise PipelineRunError('character_final_review_invalid')
    if set(body)!=keys: raise PipelineRunError('character_final_review_invalid')
    with manager._lock:
        manager.projects.get_project(project)
        current=overview(manager,project)
        if body['expected_head_sha256']!=current['head_sha256']:
            raise PipelineRunError('character_final_review_conflict')
        decisions=[]; digest=None; options={}
        if body['action']=='replace':
            regions=body['regions']
            if (type(regions) is not list or not 0<len(regions)<=64
                    or any(type(r) is not dict or set(r)!={'layer_id','region_id'}
                           or any(type(v) is not str for v in r.values()) for r in regions)):
                raise PipelineRunError('character_final_review_invalid')
            result=manager.get(project,body['job_id']); digest=body['expected_artifact_sha256']
            if result['status']!='needs_review' or result.get('artifact_sha256')!=digest:
                raise PipelineRunError('character_final_review_conflict')
            files=manager.verified_files(project,body['job_id'])
            request=read_document(manager._path(body['job_id'])/'request.json')
            options={k:request[k] for k in ('motion_choice_id','residual_texture_profile','skirt_profile') if k in request}
            doc=json.loads(files['skeleton.json'])
            for r in regions:
                slot=r['region_id']; attachment=doc['skins'][0]['attachments'][slot][slot]
                decisions.append(dict(schema='autospine.region-exclusion/v1',decision_source='human_confirmation',
                    source_bundle_sha256=digest,manifest_sha256=sha256(files['character-manifest.json']).hexdigest(),
                    **r,image_sha256=sha256(files['images/'+attachment.get('path',slot)+'.png']).hexdigest(),reversible=True))
            apply_batch(files,decisions)
        elif not current['active']:
            return current
        doc=dict(schema=SCHEMA,project_id=project,revision=0 if current['review'] is None else current['review']['revision']+1,
            previous_sha256=current['head_sha256'],source_bundle_sha256=digest,decisions=decisions,build_options=options,
            decision_source='human_confirmation',authority='none',production_authorized=False)
        root=directory(manager.root/'final-region-decisions'/project,create=True)
        if not publish_document(root/f'{doc["revision"]:06d}.json',doc,staging=root/'staging'):
            raise PipelineRunError('character_final_review_conflict')
        return overview(manager,project)


def apply_saved(manager,request,result):
    current=overview(manager,request['project_id'])
    if current['head_sha256']!=request.get('final_region_decisions_sha256'):
        raise PipelineRunError('character_final_decisions_changed')
    if not current['active']: return result
    review=current['review']
    if review['source_bundle_sha256']!=result['artifact_sha256']:
        raise PipelineRunError('character_final_source_changed')
    store=manager.application.store
    output=apply_batch(store.read(result['artifact_sha256']),review['decisions'])
    final=dict(result,artifact_sha256=store.publish(output),manifest=json.loads(output['character-manifest.json']),
        final_region_exclusions=dict(review_sha256=current['head_sha256'],
            excluded_region_ids=sorted(d['region_id'] for d in review['decisions']),authority='none'))
    # Earlier transfer counters describe the pre-exclusion material inventory.
    if 'texture_trial' in final:
        final['texture_trial']={**final['texture_trial'],'scope':'before_final_region_exclusions'}
    return final
