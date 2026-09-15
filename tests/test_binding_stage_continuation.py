from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch
from autospine_workbench.automation.binding_stage_continuation import continue_after_review


class BindingStageContinuationTests(TestCase):
    def test_save_continues_with_new_identity_and_returns_fresh_state(self):
        before=dict(can_build=True,resolved_project_sha256='r',input_identity_sha256='new-joints')
        after=dict(before,input_identity_sha256='new-bindings')
        app=SimpleNamespace(projects=object(),overview=Mock(side_effect=[before,after]))
        with patch('autospine_workbench.automation.binding_stage_continuation.prepare_and_apply',
                   return_value=dict(status='succeeded',changed=True)) as apply:
            result=continue_after_review(app,'p',{'changed':True})
        apply.assert_called_once_with(app.projects,'p','r','new-joints')
        self.assertEqual(result['input_identity_sha256'],'new-bindings')
        self.assertTrue(result['joint_review_result']['changed'])
        self.assertTrue(result['binding_auto_result']['changed'])

    def test_unreviewed_skeleton_does_not_auto_continue(self):
        app=SimpleNamespace(overview=Mock(return_value={'can_build':False}))
        with patch('autospine_workbench.automation.binding_stage_continuation.prepare_and_apply') as apply:
            result=continue_after_review(app,'p',{'changed':True})
        apply.assert_not_called()
        self.assertEqual(result['binding_auto_result']['status'],'needs_review')

    def test_later_failure_does_not_claim_joint_save_failed(self):
        app=SimpleNamespace(projects=object(),overview=Mock(return_value=dict(
            can_build=True,resolved_project_sha256='r',input_identity_sha256='i')))
        with patch('autospine_workbench.automation.binding_stage_continuation.prepare_and_apply',
                   side_effect=RuntimeError('private internals')):
            result=continue_after_review(app,'p',{'changed':True})
        self.assertTrue(result['joint_review_result']['changed'])
        self.assertEqual(result['binding_auto_result']['reason_code'],'binding_auto_interrupted')
