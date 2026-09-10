"""Orchestration gates tested with a controlled runner, never inference evidence."""

from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from autospine_workbench.automation.animated_inputs import AnimatedSourceError
from autospine_workbench.automation.input_preparation_application import InputPreparationApplication
from autospine_workbench.automation.input_preparation_runner import PosePreparationError
from autospine_workbench.automation.pipeline_run import PipelineRunError


class InputPreparationApplicationTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.store = SimpleNamespace(state_root=Path(temporary.name))
        self.checkpoint = {'resolved_project_sha256': 'a'*64, 'input_identity_sha256': 'b'*64}
        self.project = {'overrides': {'revision': 0}}
        self.config = Mock()
        self.config.public_status.return_value = {'status': 'ready', 'reason_code': None}
        self.app = InputPreparationApplication(self.store, self.config)
        self.context = SimpleNamespace(composite=b'exact-source',
                                       candidate={'composite_sha256': 'c'*64}, assert_current=Mock())
        base = 'autospine_workbench.automation.input_preparation_application.'
        self.check = self.mock(base+'_checkpoint', side_effect=lambda *_: (self.project, deepcopy(self.checkpoint)))
        self.inspect = self.mock(base+'inspect_registration', side_effect=AnimatedSourceError('animated_source_missing'))
        self.source = self.mock(base+'prepare_source', return_value=self.context)
        self.runner = self.mock(base+'run_project_pose', return_value={'test_only_pose': True})
        self.publish = self.mock(base+'publish_prepared_source', return_value={
            'source_registered': True, 'input_identity_sha256': 'd'*64,
            'registration_sha256': 'e'*64, 'reviewed_joint_count': 0, 'authority': 'none',
            'production_authorized': False, 'skeleton_status': 'blocked', 'reason_codes': ['joint_review_required']})

    def mock(self, target, **kwargs):
        patcher = patch(target, **kwargs)
        value = patcher.start()
        self.addCleanup(patcher.stop)
        return value

    def prepare(self, **kwargs):
        return self.app.prepare('project', 'a'*64, **kwargs)

    def test_cancel_before_source_and_after_source_never_runs_model_or_registers(self):
        result = self.prepare(cancel_requested=lambda: True)
        self.assertEqual(result['status'], 'canceled')
        self.source.assert_not_called()
        self.runner.assert_not_called()
        self.publish.assert_not_called()
        result = self.prepare(cancel_requested=lambda: self.source.called)
        self.assertFalse(result['source_registered'])
        self.runner.assert_not_called()
        self.publish.assert_not_called()

    def test_cancel_after_inference_or_runner_cancel_never_registers(self):
        result = self.prepare(cancel_requested=lambda: self.runner.called)
        self.assertEqual(result['status'], 'canceled')
        self.context.assert_current.assert_called_once()
        self.publish.assert_not_called()
        self.runner.side_effect = PosePreparationError('pipeline_canceled')
        with self.assertRaisesRegex(PosePreparationError, 'pipeline_canceled'):
            self.prepare()
        self.publish.assert_not_called()

    def test_stale_initial_request_and_source_changed_during_inference_never_register(self):
        with self.assertRaisesRegex(PipelineRunError, 'input_preparation_source_stale'):
            self.app.prepare('project', 'f'*64)
        self.runner.assert_not_called()
        self.context.assert_current.side_effect = AnimatedSourceError('input_preparation_source_stale')
        with self.assertRaisesRegex(AnimatedSourceError, 'input_preparation_source_stale'):
            self.prepare()
        self.runner.assert_called_once()
        self.publish.assert_not_called()

    def test_existing_registration_does_not_rerun_or_overwrite(self):
        self.inspect.side_effect = None
        self.inspect.return_value = {'source_addresses': {'input_identity_sha256': 'd'*64}}
        result = self.prepare()
        self.assertEqual(result['reason_code'], 'input_preparation_already_registered')
        self.assertTrue(result['source_registered'])
        self.source.assert_not_called()
        self.runner.assert_not_called()
        self.publish.assert_not_called()
        self.config.public_status.assert_not_called()

    def test_ready_result_retains_zero_reviewed_and_precise_runner_binding(self):
        progress = []
        result = self.prepare(progress=progress.append)
        self.assertEqual(result['status'], 'needs_review')
        self.assertEqual(result['reviewed_joint_count'], 0)
        self.assertFalse(result['production_authorized'])
        self.runner.assert_called_once()
        arguments = self.runner.call_args.args
        self.assertEqual(arguments[:5], (self.config, 'project', b'exact-source', 'c'*64, self.store.state_root))
        self.publish.assert_called_once_with(self.store, 'project', self.context, {'test_only_pose': True})
        self.assertEqual([s['status'] for s in progress[-1]], ['succeeded']*3)
        self.assertEqual(progress[0][0]['status'], 'running')

    def test_overview_distinguishes_missing_runner_edited_and_already_registered(self):
        self.assertTrue(self.app.overview('project')['can_prepare'])
        self.config.public_status.return_value = {'status':'missing', 'reason_code':'pose_runner_not_configured'}
        self.assertEqual(self.app.overview('project')['status'], 'runner_unavailable')
        self.project['overrides']['revision'] = 1
        self.project['overrides']['split_decisions'] = {'layer-000': {}}
        self.assertEqual(self.app.overview('project')['reason_code'], 'input_preparation_authoring_edits_unsupported')
        self.inspect.side_effect = None
        self.inspect.return_value = {}
        self.assertEqual(self.app.overview('project')['status'], 'already_prepared')

    def test_stale_source_when_existing_registration_is_checked_cannot_short_circuit(self):
        def changed(*_):
            self.checkpoint['resolved_project_sha256'] = 'f'*64
            return {'source_addresses': {'input_identity_sha256': 'd'*64}}
        self.inspect.side_effect = changed
        with self.assertRaisesRegex(PipelineRunError, 'input_preparation_source_stale'):
            self.prepare()
        self.runner.assert_not_called()
        self.publish.assert_not_called()

    def test_schemas_match_public_requests_overviews_and_real_application_results(self):
        import jsonschema
        from autospine_workbench.automation.input_preparation_jobs import response
        root = Path(__file__).resolve().parents[1]/'schemas'
        def validator(name):
            schema = json.loads((root/(name+'-v1.schema.json')).read_text())
            jsonschema.Draft202012Validator.check_schema(schema)
            return jsonschema.Draft202012Validator(schema)
        request = validator('input-preparation-request')
        request.validate({'expected_resolved_sha256':'a'*64})
        with self.assertRaises(jsonschema.ValidationError):
            request.validate({'expected_resolved_sha256':'a'*64, 'python':'untrusted.exe'})
        overview = validator('input-preparation-overview')
        overview.validate(self.app.overview('project'))
        self.config.public_status.return_value = {'status':'missing','reason_code':'pose_runner_not_configured'}
        overview.validate(self.app.overview('project'))
        job = validator('input-preparation-job')
        journal_request = {'project_id':'project','expected_resolved_sha256':'a'*64}
        for status in ('pending','running','blocked','failed','canceled'):
            job.validate(response('job-'+'a'*32,journal_request,status))
        for result in (self.prepare(), self.app._canceled()):
            value = response('job-'+'a'*32,journal_request,result['status'])
            value.update(result=result, source_registered=result['source_registered'], reason_code=result.get('reason_code'))
            job.validate(value)
        self.inspect.side_effect = None
        self.inspect.return_value = {'source_addresses': {'input_identity_sha256':'d'*64}}
        overview.validate(self.app.overview('project'))
        result = self.prepare()
        value = response('job-'+'a'*32,journal_request,result['status'])
        value.update(result=result,source_registered=True,reason_code=result['reason_code'])
        job.validate(value)


if __name__ == '__main__':
    unittest.main()
