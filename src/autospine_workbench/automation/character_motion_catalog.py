"""Small exact-source motion catalog; selection remains preview-only."""
import json
from ..manifest_artifacts import require_safe_token, require_sha256
from ..resolved_project import canonical_sha256
from ..targets.character43.motion_composition import compose
from .character_region_decisions import overview as regions
from .storage_io import directory, publish_document, read_document
from .pipeline_run import PipelineRunError


def folder(manager, project, create=False):
    require_safe_token(project, 'project')
    return directory(manager.root/'motion-catalog'/project, create=create)


def register(manager, project, base_digest, motion_digest, sources):
    base = manager.application.store.read(base_digest); motion = manager.application.store.read(motion_digest)
    manifest = json.loads(base['character-manifest.json'])
    if any(manifest['source_addresses'][k] != sources[k] for k in ('resolved_project_sha256', 'input_identity_sha256')):
        raise PipelineRunError('character_motion_source_changed')
    compose(base, motion, base_digest, motion_digest)
    doc = dict(schema='autospine.character-motion-choice/v1', project_id=project, authority='none',
               source_character_sha256=base_digest, motion_candidate_sha256=motion_digest,
               resolved_project_sha256=sources['resolved_project_sha256'], input_identity_sha256=sources['input_identity_sha256'],
               region_decisions_sha256=regions(manager, project)['head_sha256'],
               animations=sorted(json.loads(motion['skeleton.json'])['animations']))
    digest = canonical_sha256(doc); root = folder(manager, project, True)
    path = root/(digest+'.json')
    if not publish_document(path, doc, staging=root/'staging') and read_document(path) != doc:
        raise PipelineRunError('character_motion_catalog_invalid')
    return digest


def read(manager, project, choice):
    require_sha256(choice, 'Motion choice')
    doc = read_document(folder(manager, project)/(choice+'.json'))
    if canonical_sha256(doc) != choice or doc.get('schema') != 'autospine.character-motion-choice/v1' \
            or doc.get('project_id') != project or doc.get('authority') != 'none':
        raise PipelineRunError('character_motion_catalog_invalid')
    return doc


def choices(manager, project, sources):
    root = manager.root/'motion-catalog'/project
    if not root.exists(): return []
    head = regions(manager, project)['head_sha256']; result = []
    for path in sorted(folder(manager, project).glob('*.json')):
        doc = read(manager, project, path.stem)
        valid = doc['region_decisions_sha256'] == head and all(doc[k] == sources[k]
                    for k in ('resolved_project_sha256', 'input_identity_sha256'))
        result.append(dict(choice_id=path.stem, animations=doc['animations'], available=valid,
                           reason_code=None if valid else 'character_motion_source_changed'))
    return result


def validate(manager, request):
    choice = request.get('motion_choice_id')
    if choice is None: return None
    doc = read(manager, request['project_id'], choice)
    if doc['resolved_project_sha256'] != request['expected_resolved_sha256'] \
            or doc['input_identity_sha256'] != request['expected_input_sha256'] \
            or doc['region_decisions_sha256'] != request.get('region_decisions_sha256'):
        raise PipelineRunError('character_motion_source_changed')
    return doc


def append_selected(manager, request, result):
    doc = validate(manager, request)
    if doc is None: return result
    if doc['source_character_sha256'] != result['artifact_sha256']:
        raise PipelineRunError('character_motion_source_changed')
    store = manager.application.store
    files = compose(store.read(result['artifact_sha256']), store.read(doc['motion_candidate_sha256']),
                    result['artifact_sha256'], doc['motion_candidate_sha256'])
    return dict(artifact_sha256=store.publish(files), manifest=json.loads(files['character-manifest.json']))
