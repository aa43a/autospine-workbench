"""The optional job stage preserves defaults and captures the new artifact."""
import json
from unittest.mock import patch

from test_character_jobs import CharacterJobsTests
from autospine_workbench.automation.character_texture_trial import PROFILE


class CharacterTextureTrialTests(CharacterJobsTests):
    def test_invalid_profile_rejected_before_job(self):
        manager = self.manager()
        for value in (True, False, '', {}, 'unknown'):
            with self.assertRaisesRegex(RuntimeError, 'character_texture_profile_invalid'):
                manager.submit('sample', 'a'*64, 'b'*64, 'sleeve-job', residual_texture_profile=value)
        self.assertEqual(list(manager.root.glob('job-*')), [])

    def test_opt_in_capture_and_original_rebuild(self):
        manager = self.manager(); captured = []
        manager.capturer = lambda *args, **kwargs: captured.append(args[2]) or {'status':'unavailable'}
        baseline = self.terminal(manager, self.submit(manager))
        def transform(files):
            manifest = json.loads(files['character-manifest.json'])
            manifest.update(layers=[], animations=['flex'])
            return {**files, 'character-manifest.json':json.dumps(manifest).encode(), 'trial.json':b'{}'}, {
                'rows':[{'counts':{'transferred':3}}]}
        with patch('autospine_workbench.targets.character43.residual_texture_transfer.build', side_effect=transform) as build:
            job = manager.submit('sample', 'a'*64, 'b'*64, 'sleeve-job', residual_texture_profile=PROFILE)
            trial = self.terminal(manager, job)
            self.assertEqual(trial['status'], 'needs_review', trial)
            self.assertEqual(trial['texture_trial']['transferred_pixels'], 3)
            self.assertNotEqual(trial['artifact_sha256'], baseline['artifact_sha256'])
            self.assertEqual(captured[-1], trial['artifact_sha256'])
            self.assertEqual(trial['layers'], baseline['layers'])
            self.assertTrue(manager.download('sample', job['job_id']).startswith(b'PK'))
            restored = self.terminal(manager, self.submit(manager))
            self.assertEqual(restored['artifact_sha256'], baseline['artifact_sha256'])
            self.assertNotIn('texture_trial', restored)
            build.assert_called_once()
        self.info['source_addresses']['input_identity_sha256'] = 'c'*64
        self.assertEqual(manager.get('sample', job['job_id'])['status'], 'blocked')
