"""Character recipes survive production boundaries without changing selected rigs."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from autospine_workbench.automation.production_character_options import (
    SKIRT_PROFILES, assert_launch, launch_options, validate)
from autospine_workbench.automation.production_driver import ProductionDriver
from autospine_workbench.automation.pipeline_run import PipelineRunError
from autospine_workbench.automation.storage_io import canonical_bytes


class CharacterOptionsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.selected = dict(artifact_sha256='original')
        self.manager = SimpleNamespace(
            _path=lambda job: self.root / job,
            verified_snapshot=Mock(side_effect=lambda project, job: (deepcopy(self.selected), [])),
            motion_target=Mock(return_value=dict(job=None)))
        self.source = dict(status='succeeded', result=dict(motion_status='compiled'))
        self.projects = SimpleNamespace(get_project=Mock(return_value=dict(resolved=dict(sha256='resolved'))))
        self.driver = ProductionDriver(SimpleNamespace(character_manager=lambda: self.manager,
            projects=self.projects, get=Mock(side_effect=lambda job: deepcopy(self.source))))
        self.body = dict(project_id='role', character_job_id=None, source_job_id='motion',
                         body_options={}, joint_config={})

    def tearDown(self):
        self.tmp.cleanup()

    def character(self, job, profile=None, *, result_profile=None):
        folder = self.root / job
        folder.mkdir(exist_ok=True)
        (folder / 'request.json').write_bytes(canonical_bytes(
            dict(project_id='role', **(dict(skirt_profile=profile) if profile is not None else {}))))
        self.selected = dict(artifact_sha256=job)
        if result_profile is not None:
            self.selected['skirt_trial'] = dict(profile=result_profile)

    def test_only_finite_profiles_and_optional_none_are_accepted(self):
        self.assertEqual(launch_options({}), {})
        for profile in SKIRT_PROFILES:
            with self.subTest(profile=profile):
                options = dict(skirt_profile=profile)
                self.assertEqual(launch_options(dict(character_options=options)), options)
        for bad in ({}, None, [], True, dict(path='C:/custom.py'), dict(skirt_profile='unrecognized'),
                    dict(skirt_profile=[]), dict(skirt_profile=True), dict(skirt_profile=0),
                    dict(skirt_profile=SKIRT_PROFILES[1], output='arbitrary')):
            with self.subTest(bad=bad), self.assertRaisesRegex(PipelineRunError, 'production_character_options_invalid'):
                self.driver.freeze(dict(self.body, character_options=bad))
        self.manager.verified_snapshot.assert_not_called()
        self.projects.get_project.assert_not_called()

    def test_freeze_keeps_recipe_detached_and_validates_changed_source(self):
        body = dict(self.body, character_options=dict(skirt_profile=SKIRT_PROFILES[2]))
        frozen = self.driver.freeze(body)
        body['character_options']['skirt_profile'] = None
        self.assertEqual(frozen['character_options']['skirt_profile'], SKIRT_PROFILES[2])
        self.driver.validate(frozen)
        self.source['result']['source_identity'] = 'changed'
        with self.assertRaisesRegex(PipelineRunError, 'production_source_changed'):
            self.driver.validate(frozen)

    def test_omission_retains_legacy_selection_without_recipe_checks(self):
        self.character('selected', SKIRT_PROFILES[1], result_profile=SKIRT_PROFILES[1])
        frozen = self.driver.freeze(dict(self.body, character_job_id='selected'))
        self.assertNotIn('character_options', frozen)
        self.assertEqual(frozen['character_sha256'], 'selected')

    def test_explicit_selected_recipe_requires_both_request_and_executed_trial(self):
        profile = SKIRT_PROFILES[2]
        for requested, actual in ((SKIRT_PROFILES[1], profile), (profile, None),
                                  (profile, SKIRT_PROFILES[1]), (None, None)):
            with self.subTest(requested=requested, actual=actual):
                self.character('selected', requested, result_profile=actual)
                with self.assertRaisesRegex(PipelineRunError, 'production_character_options_mismatch'):
                    self.driver.freeze(dict(self.body, character_job_id='selected',
                        character_options=dict(skirt_profile=profile)))
        self.character('selected', profile, result_profile=profile)
        frozen = self.driver.freeze(dict(self.body, character_job_id='selected',
            character_options=dict(skirt_profile=profile)))
        self.assertEqual(frozen['character_sha256'], 'selected')

    def test_explicit_none_cannot_silently_reuse_a_skirt_trial(self):
        self.character('selected', SKIRT_PROFILES[2], result_profile=SKIRT_PROFILES[2])
        with self.assertRaisesRegex(PipelineRunError, 'production_character_options_mismatch'):
            self.driver.freeze(dict(self.body, character_job_id='selected',
                                    character_options=dict(skirt_profile=None)))
        self.character('plain')
        self.driver.freeze(dict(self.body, character_job_id='plain', character_options=dict(skirt_profile=None)))

    def test_revision_inherits_recipe_but_verifies_the_latest_candidate(self):
        profile = SKIRT_PROFILES[2]
        frozen = self.driver.freeze(dict(self.body, character_options=dict(skirt_profile=profile)))
        self.character('latest', profile, result_profile=profile)
        self.manager.motion_target.return_value = dict(job=dict(job_id='latest', status='needs_review'))
        revised = self.driver.revision_request(frozen, config=dict(hair=False), body_options=dict(yaw=10))
        self.assertEqual(revised['character_job_id'], 'latest')
        self.assertEqual(revised['character_options'], frozen['character_options'])
        self.assertEqual(revised['joint_config'], dict(hair=False))
        self.assertEqual(revised['body_options'], dict(yaw=10))
        self.character('latest', SKIRT_PROFILES[1], result_profile=SKIRT_PROFILES[1])
        with self.assertRaisesRegex(PipelineRunError, 'production_character_options_mismatch'):
            self.driver.revision_request(frozen)

    def test_revision_omission_keeps_historical_latest_candidate_behavior(self):
        self.character('original')
        frozen = self.driver.freeze(dict(self.body, character_job_id='original'))
        self.character('latest', SKIRT_PROFILES[2], result_profile=SKIRT_PROFILES[2])
        self.manager.motion_target.return_value = dict(job=dict(job_id='latest', status='needs_review'))
        revised = self.driver.revision_request(frozen)
        self.assertEqual(revised['character_job_id'], 'latest')
        self.assertNotIn('character_options', revised)

    def test_reserved_launch_recipe_cannot_change_during_resume(self):
        request = dict(character_options=dict(skirt_profile=SKIRT_PROFILES[2]))
        assert_launch(request, dict(skirt_profile=SKIRT_PROFILES[2]))
        for launch in ({}, dict(skirt_profile=None), dict(skirt_profile=SKIRT_PROFILES[1])):
            with self.subTest(launch=launch), self.assertRaisesRegex(PipelineRunError, 'production_character_options_mismatch'):
                assert_launch(request, launch)
        # Old journals contain no recipe and keep the original launch behavior.
        assert_launch({}, dict(skirt_profile=SKIRT_PROFILES[1]))

    def test_persisted_recipe_survives_retry_and_restart(self):
        from autospine_workbench.automation.production_jobs import ProductionJobs
        request = self.driver.freeze(dict(self.body,
            character_options=dict(skirt_profile=SKIRT_PROFILES[2])))
        root = self.root / 'production'
        manager = ProductionJobs(root, self.driver)
        try:
            value = manager.journal.create(request)
            for stage in ('source', 'bindings'):
                value['stages'][stage]['status'] = 'succeeded'
            value['stages']['character'].update(status='failed', job_id='failed',
                launch=dict(skirt_profile=SKIRT_PROFILES[2]), attempts=[dict(job_id='failed')])
            value['status'] = 'blocked'
            value = manager.journal.append(value, 'character_failed')
            with patch.object(manager, '_schedule'), patch.object(self.driver, 'exists', return_value=False):
                retry = manager.retry(value['run_id'], value['revision'])
            self.assertEqual(retry['request'], request)
            self.assertNotIn('job_id', retry['stages']['character'])
            self.assertEqual(retry['stages']['character']['attempts'], [dict(job_id='failed')])
        finally:
            manager.close()
        restored = ProductionJobs(root, self.driver)
        try:
            current = restored.get(value['run_id'])
            with patch.object(restored, '_schedule'):
                resumed = restored.resume(current['run_id'], current['revision'])
            self.assertEqual(resumed['request']['character_options'], request['character_options'])
        finally:
            restored.close()

    def test_source_and_candidate_revision_keeps_recipe_and_resets_acceptance(self):
        from autospine_workbench.automation.production_jobs import ProductionJobs
        profile = SKIRT_PROFILES[2]
        self.character('original', profile, result_profile=profile)
        request = self.driver.freeze(dict(self.body, character_job_id='original',
                                         character_options=dict(skirt_profile=profile)))
        manager = ProductionJobs(self.root / 'production', self.driver)
        try:
            value = manager.journal.create(request)
            value['stages']['character'].update(status='succeeded', job_id='original', artifact_sha256='original')
            for stage in ('source', 'bindings', 'body', 'joint'):
                value['stages'][stage]['status'] = 'succeeded'
            value['stages']['review'].update(status='stage_accepted', decision='accepted_with_exceptions')
            value['status'] = 'stage_accepted'
            value = manager.journal.append(value, 'accepted')
            self.character('latest', profile, result_profile=profile)
            self.manager.motion_target.return_value = dict(job=dict(job_id='latest', status='needs_review'))
            self.source['result']['source_identity'] = 'new-source'
            with patch.object(manager, '_schedule'):
                revised = manager.revise(value['run_id'], value['revision'])
            self.assertEqual(revised['request']['character_options'], request['character_options'])
            self.assertEqual(revised['request']['character_job_id'], 'latest')
            self.assertNotEqual(revised['request']['source_sha256'], request['source_sha256'])
            self.assertFalse(revised['revision_plan']['acceptance_inherited'])
            self.assertEqual(revised['revision_plan']['reset_stages'], ['review', 'delivery'])
            self.assertEqual(revised['stages']['review']['status'], 'pending')
            self.assertEqual(manager.get(value['run_id']), value)
        finally:
            manager.close()


if __name__ == '__main__':
    unittest.main()
