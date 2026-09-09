"""Prepare project-local candidate sources without manufacturing reviewed joints."""
from copy import deepcopy

from ..resolved_project import canonical_sha256
from .animated_inputs import AnimatedSourceError, _checkpoint
from .animated_input_index import inspect_registration
from .input_preparation_jobs import STEPS
from .input_preparation_runner import PoseRunnerConfig, run_project_pose
from .input_preparation_sources import prepare_source, publish_prepared_source
from .pipeline_lease import execution_lease
from .pipeline_run import PipelineRunError


class InputPreparationApplication:
    def __init__(self, store, config=None):
        self.store = store
        self.config = config if config is not None else PoseRunnerConfig.from_environment()

    def overview(self, project_id):
        project, checkpoint = _checkpoint(self.store, project_id)
        value = dict(schema='autospine.input-preparation-overview/v1', project_id=project_id,
                     resolved_project_sha256=checkpoint['resolved_project_sha256'], status='unsupported',
                     can_prepare=False, source_registered=False, reason_code=None, authority='none')
        try:
            inspect_registration(self.store, project_id)
        except AnimatedSourceError as exc:
            if exc.reason_code != 'animated_source_missing':
                value['reason_code'] = exc.reason_code
                return value
        else:
            value.update(status='already_prepared', source_registered=True)
            return value
        if project['overrides']['revision'] != 0:
            value['reason_code'] = 'input_preparation_authoring_edits_unsupported'
            return value
        runner = self.config.public_status()
        if runner['status'] != 'ready':
            value.update(status='runner_unavailable', reason_code=runner['reason_code'])
            return value
        value.update(status='ready', can_prepare=True)
        return value

    def prepare(self, project_id, expected_resolved_sha256, cancel_requested=lambda: False,
                progress=lambda steps: None):
        _, checkpoint = _checkpoint(self.store, project_id)
        if checkpoint['resolved_project_sha256'] != expected_resolved_sha256:
            raise PipelineRunError('input_preparation_source_stale')
        # A lease serializes separate managers/processes for exactly the same source.
        run_id = 'run-' + canonical_sha256({'operation': 'input-preparation-v1',
                                           'project_id': project_id, 'checkpoint': checkpoint})
        with execution_lease(self.store.state_root, run_id):
            if cancel_requested():
                return self._canceled()
            try:
                current = inspect_registration(self.store, project_id)
            except AnimatedSourceError as exc:
                if exc.reason_code != 'animated_source_missing':
                    raise
            else:
                if _checkpoint(self.store, project_id)[1] != checkpoint:
                    raise PipelineRunError('input_preparation_source_stale')
                return dict(status='needs_review', source_registered=True, authority='none',
                            reason_code='input_preparation_already_registered',
                            input_identity_sha256=current['source_addresses']['input_identity_sha256'])
            steps = [dict(id=name, status='pending') for name in STEPS]
            def step(index, status):
                steps[index]['status'] = status
                progress(deepcopy(steps))
            step(0, 'running')
            context = prepare_source(self.store, project_id, expected_resolved_sha256)
            step(0, 'succeeded')
            if cancel_requested():
                return self._canceled()
            step(1, 'running')
            pose = run_project_pose(self.config, project_id, context.composite,
                                    context.candidate['composite_sha256'], self.store.state_root,
                                    cancel_requested)
            context.assert_current()
            step(1, 'succeeded')
            if cancel_requested():
                return self._canceled()
            step(2, 'running')
            result = publish_prepared_source(self.store, project_id, context, pose)
            step(2, 'succeeded')
            return dict(result, status='needs_review', reason_code='joint_review_required')

    @staticmethod
    def _canceled():
        return dict(status='canceled', source_registered=False, authority='none',
                    reason_code='preparation_canceled')
