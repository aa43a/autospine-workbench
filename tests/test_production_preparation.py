"""Preparation never overwrites a selected character or invents joint review."""
from copy import deepcopy
from types import SimpleNamespace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from autospine_workbench.automation.production_preparation import prepare
from autospine_workbench.automation.pipeline_run import PipelineRunError
from autospine_workbench.automation.production_character_options import SKIRT_PROFILES
from autospine_workbench.automation.storage_io import canonical_bytes


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

    def test_sleeve_selection_race_does_not_submit_another_candidate(self):
        driver,value,write,_=self.fixture()
        for key in ('source','bindings'):
            value['stages'][key]['status']='succeeded'
        value['stages']['sleeves']=dict(status='succeeded',job_id='original')
        manager=driver.motions.character_manager.return_value
        manager.overview.return_value=dict(can_build=True,sleeve_job_id='replacement')
        with patch('autospine_workbench.automation.production_sleeves.prepare',return_value=True):
            with self.assertRaisesRegex(PipelineRunError,'production_sleeve_selection_changed'):
                prepare(driver,lambda:value,write,lambda:False)
        manager.submit.assert_not_called()

    def test_cancellation_during_character_submission_respects_ownership(self):
        for shared in (False,True):
            with self.subTest(shared=shared),TemporaryDirectory() as folder:
                driver,value,write,_=self.fixture()
                for key in ('source','bindings'):
                    value['stages'][key]['status']='succeeded'
                manager=driver.motions.character_manager.return_value
                manager.root=Path(folder)
                manager.overview.return_value=dict(can_build=True,sleeve_job_id=None,
                    expected_resolved_sha256='r',expected_input_sha256='i')
                def submit(*args,**kwargs):
                    value['status']='canceled'
                    return dict(job_id='shared' if shared else value['stages']['character']['job_id'])
                manager.submit.side_effect=submit
                self.assertFalse(prepare(driver,lambda:value,write,lambda:value.get('status')=='canceled'))
                self.assertEqual(manager.cancel.call_count,0 if shared else 1)
                self.assertEqual(value['stages']['character']['shared'],shared)

    def test_explicit_recipe_is_reserved_submitted_and_recovers_without_resubmitting(self):
        for profile in (None, SKIRT_PROFILES[2]):
            with self.subTest(profile=profile),TemporaryDirectory() as folder:
                driver,value,write,events=self.fixture()
                value['request']['character_options']=dict(skirt_profile=profile)
                for stage in ('source','bindings'):
                    value['stages'][stage]['status']='succeeded'
                manager=driver.motions.character_manager.return_value
                manager.root=Path(folder)
                manager._path.side_effect=lambda job:manager.root/job
                manager.overview.return_value=dict(can_build=True,sleeve_job_id=None,
                    expected_resolved_sha256='r',expected_input_sha256='i')
                manager.get.return_value=dict(status='needs_review')
                verified=dict(artifact_sha256='candidate')
                if profile is not None:verified['skirt_trial']=dict(profile=profile)
                manager.verified_snapshot.return_value=(verified, [])
                def submit(project,**kwargs):
                    self.assertEqual(kwargs['skirt_profile'],profile)
                    job=value['stages']['character']['job_id']
                    target=manager.root/job;target.mkdir()
                    (target/'request.json').write_bytes(canonical_bytes(dict(project_id=project,
                        **(dict(skirt_profile=profile) if profile is not None else {}))))
                    return dict(job_id=job)
                manager.submit.side_effect=submit
                self.assertTrue(prepare(driver,lambda:value,write,lambda:False))
                self.assertEqual(value['stages']['character']['launch']['skirt_profile'],profile)
                self.assertEqual(value['stages']['character']['artifact_sha256'],'candidate')
                self.assertIn('character_reserved',events)
                # Simulate a process restart after reservation: persisted launch and
                # request bind the same child, rather than starting another job.
                value['stages']['character']['status']='running'
                manager.overview.reset_mock();manager.submit.reset_mock()
                self.assertTrue(prepare(driver,lambda:value,write,lambda:False))
                manager.overview.assert_not_called();manager.submit.assert_not_called()

    def test_changed_reserved_recipe_stops_before_character_submission(self):
        with TemporaryDirectory() as folder:
            driver,value,write,_=self.fixture()
            value['request']['character_options']=dict(skirt_profile=SKIRT_PROFILES[2])
            for stage in ('source','bindings'):
                value['stages'][stage]['status']='succeeded'
            value['stages']['character'].update(job_id='reserved',launch=dict(skirt_profile=None))
            manager=driver.motions.character_manager.return_value;manager.root=Path(folder)
            with self.assertRaisesRegex(PipelineRunError,'production_character_options_mismatch'):
                prepare(driver,lambda:value,write,lambda:False)
            manager.submit.assert_not_called();manager.get.assert_not_called()

    def test_legacy_published_child_without_launch_keeps_recovery_behavior(self):
        with TemporaryDirectory() as folder:
            driver,value,write,_=self.fixture()
            for stage in ('source','bindings'):
                value['stages'][stage]['status']='succeeded'
            value['stages']['character'].update(job_id='published',status='running')
            target=Path(folder)/'published';target.mkdir()
            (target/'request.json').write_bytes(canonical_bytes(dict(project_id='new-role')))
            manager=driver.motions.character_manager.return_value;manager.root=Path(folder)
            manager.get.return_value=dict(status='needs_review')
            manager.verified_snapshot.return_value=(dict(artifact_sha256='candidate'), [])
            self.assertTrue(prepare(driver,lambda:value,write,lambda:False))
            self.assertEqual(value['stages']['character']['artifact_sha256'],'candidate')
            manager.submit.assert_not_called();manager.overview.assert_not_called()

    def test_selected_recipe_mismatch_does_not_mark_preparation_reused(self):
        with TemporaryDirectory() as folder:
            driver,value,write,events=self.fixture('existing')
            value['request']['character_options']=dict(skirt_profile=SKIRT_PROFILES[2])
            target=Path(folder)/'existing';target.mkdir()
            (target/'request.json').write_bytes(canonical_bytes(dict(project_id='new-role')))
            manager=driver.motions.character_manager.return_value
            manager._path.return_value=target
            manager.verified_snapshot.return_value=(dict(artifact_sha256='sha'), [])
            with self.assertRaisesRegex(PipelineRunError,'production_character_options_mismatch'):
                prepare(driver,lambda:value,write,lambda:False)
            self.assertEqual(events,[])
            self.assertEqual(value['stages']['bindings']['status'],'pending')
            manager.submit.assert_not_called()
