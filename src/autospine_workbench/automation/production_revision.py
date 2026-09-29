"""Explain and pin dependency-aware rebuilds before changing any job."""
from ..resolved_project import canonical_sha256
from .pipeline_run import PipelineRunError


def plan(manager,run_id,revision,joint_config=None,body_options=None):
    previous=manager.get(run_id)
    if type(revision) is not int or previous['revision']!=revision:
        raise PipelineRunError('production_revision_conflict')
    request=manager.driver.revision_request(previous['request'],joint_config,body_options)
    character=previous['stages']['character']
    same_character=(request['project_id']==previous['request']['project_id'] and
        request.get('character_sha256') is not None and character.get('artifact_sha256')==request['character_sha256']
        and character.get('job_id')==request.get('character_job_id'))
    reuse=[]
    if same_character:
        # Older runs predate source/binding stage records. The verified character
        # already contains those inputs; do not promise a rebuild that preparation skips.
        reuse=['source','bindings','character']
        old=previous['request']
        if (all(old.get(k)==request.get(k) for k in ('source_job_id','source_sha256','body_options'))
                and previous['stages']['body']['status']=='succeeded'):
            reuse.append('body')
    refresh=['source','bindings','character'] if not same_character and request.get('character_sha256') else []
    value=dict(parent_run_id=run_id,parent_revision=revision,request=request,reuse_stages=reuse,refresh_stages=refresh,
        rebuild_stages=[s for s in ('source','bindings','character','body','joint') if s not in reuse+refresh],
        reset_stages=['review','delivery'],old_candidate_preserved=True,acceptance_inherited=False)
    return dict(value,plan_sha256=canonical_sha256(value))
