"""New UI requests an automatic strategy; old frozen drafts retain their solver."""
from .pipeline_run import PipelineRunError
from .storage_io import read_document
from ..targets.character43.final_leg_repair_policy import select


def choose(manager, job, body):
    if 'automatic_strategy' not in body: return None
    if body['automatic_strategy'] is not True or body['action'] != 'local_repair':
        raise PipelineRunError('motion_local_solver_request_invalid')
    from .motion_target_jobs import context, assert_current
    result, files = context(manager, job)
    if body['artifact_sha256'] != result['artifact_sha256']:
        raise PipelineRunError('motion_local_solver_candidate_changed')
    assert_current(manager, read_document(manager.folder(job)/'request.json'))
    try: return select(files, body['slot'], body['animation'])
    except ValueError as error: raise PipelineRunError(str(error)) from error
