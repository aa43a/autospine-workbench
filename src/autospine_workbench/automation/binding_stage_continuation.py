"""Continue safe binding policies after a committed joint review."""
from .binding_auto_workflow import prepare_and_apply


def continue_after_review(application, project, result):
    # The joint transaction has already committed. Report a later failure separately.
    current=application.overview(project)
    operation=dict(status='needs_review', changed=False, reason_code='joint_review_required',
                   authority='none', production_authorized=False)
    if current.get('can_build'):
        try:
            operation=prepare_and_apply(application.projects,project,
                current['resolved_project_sha256'],current['input_identity_sha256'])
        except (ValueError,RuntimeError,OSError) as exc:
            operation.update(status='stopped',reason_code=getattr(exc,'reason_code','binding_auto_interrupted'))
        current=application.overview(project)
    return {**current,'joint_review_result':result,'binding_auto_result':operation}
