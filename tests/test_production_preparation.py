"""Preparation never overwrites a selected character or invents joint review."""
from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from autospine_workbench.automation.production_preparation import prepare
from autospine_workbench.automation.pipeline_run import PipelineRunError


class PreparationTests(unittest.TestCase):
    def fixture(self, existing=None):
        value=dict(request=dict(project_id='new-role',character_job_id=existing,
            character_sha256='sha',resolved_sha256='resolved'),stages={
            s:dict(status='pending',attempts=[]) for s in ('source','bindings','character')})
        projects=object()
        driver=SimpleNamespace(motions=SimpleNamespace(projects=projects,character_manager=Mock()))
        events=[]
        def write(change,event):
            change(value);events.append(event)
        return driver,value,write,events

    def test_existing_selection_is_reused_without_auto_rebinding(self):
        driver,value,write,events=self.fixture('job-existing')
        self.assertTrue(prepare(driver,lambda:value,write,lambda:False))
        self.assertEqual(value['stages']['character']['job_id'],'job-existing')
        self.assertEqual(value['stages']['bindings']['status'],'reused')
        self.assertEqual(events,['character_reused'])

    def test_unreviewed_joints_stop_before_binding_mutations(self):
        driver,value,write,events=self.fixture()
        with patch('autospine_workbench.automation.input_preparation_application.InputPreparationApplication') as app, \
             patch('autospine_workbench.automation.production_preparation.inspect_registration',
                   return_value={'skeleton_status':'pending'}), \
             patch('autospine_workbench.automation.binding_auto_workflow.prepare_and_apply') as bindings:
            app.return_value.prepare.return_value={'source_registered':True}
            with self.assertRaisesRegex(PipelineRunError,'joint_review_required'):
                prepare(driver,lambda:value,write,lambda:False)
            bindings.assert_not_called()
        self.assertEqual(value['stages']['source']['status'],'succeeded')
        self.assertEqual(value['stages']['bindings']['status'],'pending')

    def test_source_failure_does_not_advance_bindings(self):
        driver,value,write,events=self.fixture()
        with patch('autospine_workbench.automation.input_preparation_application.InputPreparationApplication') as app:
            app.return_value.prepare.return_value={'source_registered':False,'reason_code':'input_preparation_canceled'}
            with self.assertRaisesRegex(PipelineRunError,'input_preparation_canceled'):
                prepare(driver,lambda:value,write,lambda:False)
        self.assertEqual(value['stages']['bindings']['status'],'pending')
