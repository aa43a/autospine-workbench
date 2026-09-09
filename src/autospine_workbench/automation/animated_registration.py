"""Validate append-only v1 registrations and explicit v2 authoring rebases."""
import math
from ..benchmark.joint_draft import JOINTS
from ..manifest_artifacts import require_sha256
from .animated_inputs import AnimatedSourceError


def validate_entry(doc, project_id, revision, previous):
    fields = {'schema', 'authority', 'production_authorized', 'project_id', 'manifest',
              'source_draft_sha256', 'checkpoint', 'revision', 'previous_sha256'}
    version = doc.get('schema')
    project_source = version == 'autospine.animated-input-registration/v3'
    if project_source:
        from .input_preparation_sources import validate_source_manifest
        validate_source_manifest(doc['manifest'])
        fields.add('source_kind')
        if 'authoring_rebase' in doc:
            fields.add('authoring_rebase')
    if version == 'autospine.animated-input-registration/v2':
        fields.add('authoring_rebase')
    if (set(doc) != fields or version not in ('autospine.animated-input-registration/v1',
                                              'autospine.animated-input-registration/v2',
                                              'autospine.animated-input-registration/v3') or
        doc['authority'] != 'none' or doc['production_authorized'] is not False or
        doc['project_id'] != project_id or type(doc['revision']) is not int or
        doc['revision'] != revision or doc['previous_sha256'] != (previous[0] if previous else None)):
        raise AnimatedSourceError('animated_source_invalid')
    require_sha256(doc['source_draft_sha256'], 'Binding draft')
    _checkpoint(doc['checkpoint'])
    if previous and doc['manifest'] != previous[1]['manifest']:
        raise AnimatedSourceError('animated_source_invalid')
    if previous and previous[1]['schema'].endswith('/v3') and not project_source:
        raise AnimatedSourceError('animated_source_invalid')
    if project_source:
        if (doc['source_kind'] != 'project_audit' or
            doc['manifest'].get('schema') != 'autospine.project-audit-source/v1' or
            doc['manifest'].get('project_id') != project_id or
            (previous and previous[1]['schema'] != version)):
            raise AnimatedSourceError('animated_source_invalid')
        if 'authoring_rebase' not in doc:
            if previous and ('authoring_rebase' in previous[1] or doc['checkpoint'] != previous[1]['checkpoint']):
                raise AnimatedSourceError('animated_source_invalid')
            return
    if version.endswith('/v1'):
        if previous and (previous[1]['schema'] != version or doc['checkpoint'] != previous[1]['checkpoint']):
            raise AnimatedSourceError('animated_source_invalid')
        return
    proof = doc['authoring_rebase']
    keys = {'schema', 'authority', 'annotation_mode', 'independent_annotation',
            'previous_registration_sha256', 'source_checkpoint', 'target_checkpoint',
            'authoring_revision', 'authoring_overrides_sha256', 'joint_overrides',
            'imported_joint_ids', 'ignored_joint_ids'}
    if (not previous or type(proof) is not dict or set(proof) != keys or
        proof['schema'] != 'autospine.animated-authoring-rebase/v1' or proof['authority'] != 'none' or
        proof['annotation_mode'] != 'model_assisted' or proof['independent_annotation'] is not False or
        proof['target_checkpoint'] != doc['checkpoint'] or
        type(proof['authoring_revision']) is not int or proof['authoring_revision'] < 0 or
        type(proof['joint_overrides']) is not dict):
        raise AnimatedSourceError('animated_source_invalid')
    require_sha256(proof['authoring_overrides_sha256'], 'Authoring overrides')
    require_sha256(proof['previous_registration_sha256'], 'Previous registration')
    _checkpoint(proof['source_checkpoint'])
    _checkpoint(proof['target_checkpoint'])
    for joint, point in proof['joint_overrides'].items():
        if (type(joint) is not str or not joint or type(point) is not dict or
            any(type(point.get(k)) not in (int, float) or not math.isfinite(point[k]) for k in ('x', 'y'))):
            raise AnimatedSourceError('animated_source_invalid')
    for field, canonical in [('imported_joint_ids', True), ('ignored_joint_ids', False)]:
        ids = proof[field]
        if (type(ids) is not list or any(type(v) is not str or (v in JOINTS) != canonical for v in ids)
            or len(ids) != len(set(ids)) or not set(ids).issubset(proof['joint_overrides'])):
            raise AnimatedSourceError('animated_source_invalid')
    old = previous[1]
    if proof != old.get('authoring_rebase'):
        if proof['previous_registration_sha256'] != previous[0] or proof['source_checkpoint'] != old['checkpoint']:
            raise AnimatedSourceError('animated_source_invalid')
    elif doc['checkpoint'] != old['checkpoint']:
        raise AnimatedSourceError('animated_source_invalid')


def _checkpoint(value):
    if type(value) is not dict or set(value) != {'resolved_project_sha256', 'input_identity_sha256'}:
        raise AnimatedSourceError('animated_source_invalid')
    for digest in value.values():
        require_sha256(digest, 'Project checkpoint')
