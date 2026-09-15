"""Recover an open editor only across unchanged, unsaved preparation revisions."""
from copy import deepcopy

from .pipeline_run import PipelineRunError
from .storage_io import read_document
from ..asset.planning.sleeve_regions import validate
from ..resolved_project import canonical_sha256


def recover(root, project, current, body, read):
    start=body['expected_revision']; end=current['revision']
    def reject(): raise PipelineRunError('sleeve_annotation_conflict')
    if type(start) is not int or not 1 <= start < end or end-start > 32: reject()
    previous_surface=previous_draft=None
    for revision in range(start,end+1):
        value=read_document(root/project/f'revision-{revision:012d}.json')
        if (value.get('project_id')!=project or value.get('revision')!=revision
                or value.get('source_sha256')!=body['expected_resolved_sha256']
                or (revision>start and value.get('saved') is not False)): reject()
        candidate=read(value['candidate_sha256']); draft=read(value['draft_sha256'])
        validate(draft,candidate)
        surface=deepcopy(candidate); surface.pop('source_sha256')
        baseline=deepcopy(draft); baseline.pop('candidate_sha256')
        if revision==start:
            validate(body['draft'],candidate)
            original_candidate=canonical_sha256(candidate)
            previous_surface,previous_draft=surface,baseline
        elif surface!=previous_surface or baseline!=previous_draft: reject()
    recovered=deepcopy(body['draft']); recovered['candidate_sha256']=canonical_sha256(candidate)
    validate(recovered,candidate)
    receipt=dict(profile='unchanged-unsaved-editor-v1',previous_revision=start,
        previous_candidate_sha256=original_candidate,submitted_draft_sha256=canonical_sha256(body['draft']),
        authority='none',production_authorized=False)
    return recovered,receipt
