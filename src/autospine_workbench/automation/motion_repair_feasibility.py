"""Bounded counterexamples from an impossible fixed-vertex local solve."""
from ..resolved_project import canonical_sha256
from .storage_io import canonical_bytes, publish_document, read_document
from .pipeline_run import PipelineRunError
from ..targets.character43.final_leg_repair_policy import PROFILE

REASON = 'motion_final_leg_fixed_vertices_infeasible'


def save(folder, request, report):
    repair = request['repair_execution']; plan = repair['draft']
    failures = report['failures']
    if (repair['profile'] != PROFILE or plan['slot'] != report['slot'] or not failures
            or report['status'] != 'infeasible_fixed_vertices'
            or canonical_sha256(plan) != repair['draft_sha256']):
        raise ValueError('motion_repair_feasibility_scope_invalid')
    # Keep a representative worst-time example for each triangle, not duplicate frames.
    worst = {}
    for row in failures:
        key = row['triangle']
        severity = max(.5-row['setup_ratio'],row['setup_ratio']-2,
                       .5-row['projected_ratio'],row['projected_ratio']-2)
        if key not in worst or severity > worst[key][0]: worst[key] = (severity,row)
    examples = [row for _,row in sorted(worst.values(),key=lambda item:item[0],reverse=True)[:24]]
    value = dict(reason_code=REASON,request_sha256=canonical_sha256(request),
        parent_job_id=repair['parent_job_id'],artifact_sha256=repair['parent_artifact_sha256'],
        draft_sha256=repair['draft_sha256'],profile=repair['profile'],slot=plan['slot'],animation=plan['animation'],
        fixed_triangles=report['fixed_triangles'],sample_count=report['sample_count'],
        failure_observations=len(failures),failed_triangles=len(worst),examples=examples,
        complete_counterexamples_sha256=canonical_sha256(report),
        candidate_generated=False,authority='none',selected=False,
        scope='necessary_fixed_vertex_counterexamples_not_full_feasibility_or_visual_quality')
    publish_document(folder/'repair-feasibility.json',value,staging=folder/'staging')


def read(manager,job):
    state=manager.get(job)
    if state['status']!='failed' or state.get('reason_code')!=REASON:
        raise PipelineRunError('motion_repair_feasibility_unavailable')
    request=read_document(manager.folder(job)/'request.json')
    value=read_document(manager.folder(job)/'repair-feasibility.json')
    repair=request['repair_execution']
    if (value['request_sha256']!=canonical_sha256(request)
            or value['draft_sha256']!=repair['draft_sha256']
            or value['artifact_sha256']!=repair['parent_artifact_sha256']
            or value['parent_job_id']!=repair['parent_job_id']
            or value['profile']!=PROFILE or repair['profile']!=PROFILE
            or value['slot']!=repair['draft']['slot'] or value['animation']!=repair['draft']['animation']
            or value['reason_code']!=REASON or value['candidate_generated'] is not False):
        raise PipelineRunError('motion_repair_feasibility_changed')
    return canonical_bytes(dict(value,job_id=job)),'application/json'
