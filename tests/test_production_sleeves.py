from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock

from autospine_workbench.automation.production_sleeves import prepare
from autospine_workbench.automation.production_submission import child_id
from autospine_workbench.automation.storage_io import canonical_bytes


class SleevePreparationTests(TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.value = dict(request=dict(project_id='p'), stages={})
        self.draft = 'a'*64
        self.latest = None
        self.events = []
        self.submitted = []
        self.manager = SimpleNamespace(root=self.root, overview=lambda p:dict(can_build=True, job=self.latest),
            _draft_sha=lambda p:self.draft, submit=self.submit,
            _assert_current=Mock(), cancel=Mock(), get=lambda p,j:dict(job_id=j,status='needs_review'))
        self.driver = SimpleNamespace(motions=SimpleNamespace(character_manager=lambda:SimpleNamespace(sleeves=self.manager)),
                                      wait=Mock())
        self.info = dict(expected_resolved_sha256='b'*64)

    def write(self, change, event):
        change(self.value); self.events.append(event)

    def submit(self, project, expected_resolved_sha256, expected_draft_sha256):
        job = child_id('job-'); self.submitted.append(job)
        self.assertEqual(self.value['stages']['sleeves']['job_id'], job)
        root = self.root/job; root.mkdir()
        (root/'request.json').write_bytes(canonical_bytes(dict(project_id=project,
            expected_resolved_sha256=expected_resolved_sha256, draft_sha256=expected_draft_sha256)))
        return dict(job_id=job)

    def run_prepare(self):
        return prepare(self.driver, lambda:self.value, self.write, lambda:False, self.info)

    def test_exact_reserved_request_recovers_without_second_submission(self):
        def crash(p,j):
            raise RuntimeError('observation interrupted')
        self.manager.get = crash
        with self.assertRaisesRegex(RuntimeError, 'observation interrupted'):
            self.run_prepare()
        first = deepcopy(self.value['stages']['sleeves'])
        self.manager.get = lambda p,j:dict(job_id=j,status='needs_review')
        self.assertTrue(self.run_prepare())
        self.assertEqual(self.submitted, [first['job_id']])
        self.assertEqual(self.value['stages']['sleeves']['status'], 'succeeded')

    def test_saved_sleeve_finishes_before_character_submission(self):
        from autospine_workbench.automation.production_preparation import prepare as prepare_character
        self.value['request'].update(character_job_id=None)
        self.value['stages'].update(source=dict(status='succeeded'), bindings=dict(status='succeeded'),
                                   character=dict(status='pending', attempts=[]))
        character_root = self.root/'characters'; character_root.mkdir()
        def overview(project):
            stage = self.value['stages'].get('sleeves', {})
            return dict(self.info, can_build=stage.get('status') == 'succeeded',
                reason_code='character_sleeve_candidate_required', expected_input_sha256='e'*64,
                sleeve_job_id=stage.get('job_id'))
        def submit(project, **launch):
            self.assertEqual(self.value['stages']['sleeves']['status'], 'succeeded')
            self.assertEqual(launch['sleeve_job_id'], self.submitted[0])
            job = child_id('job-'); folder = character_root/job; folder.mkdir()
            (folder/'request.json').write_bytes(canonical_bytes(launch))
            return dict(job_id=job)
        manager = SimpleNamespace(root=character_root, sleeves=self.manager, overview=overview,
            submit=submit, get=lambda p,j:dict(status='needs_review'),
            verified_snapshot=lambda p,j:(dict(artifact_sha256='f'*64), None))
        self.driver.motions.character_manager = lambda:manager
        self.assertTrue(prepare_character(self.driver, lambda:self.value, self.write, lambda:False))
        self.assertLess(self.events.index('sleeves_prepared'), self.events.index('character_reserved'))
        self.assertEqual(self.value['stages']['character']['artifact_sha256'], 'f'*64)

    def test_changed_saved_draft_blocks_reserved_job(self):
        self.run_prepare(); self.draft = 'c'*64
        with self.assertRaisesRegex(RuntimeError, 'sleeve_draft_changed'):
            self.run_prepare()
        self.assertEqual(len(self.submitted), 1)

    def test_unsaved_and_withdrawn_never_submit(self):
        self.manager.overview = lambda p:dict(can_build=False)
        with self.assertRaisesRegex(RuntimeError, 'sleeve_annotation_required'):
            self.run_prepare()
        self.manager.overview = lambda p:dict(can_build=True,job=dict(candidate_withdrawn=True))
        with self.assertRaisesRegex(RuntimeError, 'sleeve_candidate_withdrawn'):
            self.run_prepare()
        self.assertEqual(self.submitted, [])

    def test_existing_active_job_attaches_but_mismatched_source_is_rejected(self):
        job = 'job-'+'d'*32
        root = self.root/job; root.mkdir()
        request = dict(project_id='p', expected_resolved_sha256='b'*64, draft_sha256='c'*64)
        (root/'request.json').write_bytes(canonical_bytes(request))
        self.latest = dict(job_id=job,status='running')
        with self.assertRaisesRegex(RuntimeError, 'production_sleeve_source_changed'):
            self.run_prepare()
        self.assertTrue(self.value['stages']['sleeves']['shared'])
        self.assertEqual(self.submitted, [])

    def test_failure_is_not_relaunched_on_resume(self):
        self.manager.get = lambda p,j:dict(job_id=j,status='blocked',reason_code='geometry_failure')
        for _ in range(2):
            with self.assertRaisesRegex(RuntimeError, 'geometry_failure'):
                self.run_prepare()
        self.assertEqual(len(self.submitted), 1)

    def test_previous_failure_becomes_a_retryable_stage(self):
        previous = 'job-'+'e'*32
        self.latest = dict(job_id=previous, status='blocked', reason_code='old_failure')
        with self.assertRaisesRegex(RuntimeError, 'old_failure'):
            self.run_prepare()
        stage = self.value['stages']['sleeves']
        self.assertEqual(stage['job_id'], previous)
        self.assertEqual(stage['status'], 'blocked')
        # Apply the coordinator's explicit retry transition, retaining history.
        stage.pop('job_id'); stage.update(status='pending')
        self.assertTrue(self.run_prepare())
        self.assertEqual(len(self.submitted), 1)
        self.assertEqual(stage['attempts'][0]['job_id'], previous)
        self.assertFalse(stage['shared'])

    def test_cancel_during_publication_cancels_owned_child(self):
        original = self.manager.submit
        def submit(*args, **kwargs):
            result = original(*args, **kwargs)
            self.value['status'] = 'canceled'
            return result
        self.manager.submit = submit
        self.assertFalse(prepare(self.driver, lambda:self.value, self.write,
            lambda:self.value.get('status') == 'canceled', self.info))
        self.manager.cancel.assert_called_once_with('p', self.submitted[0])

    def test_stop_during_shared_observation_does_not_cancel_borrowed_job(self):
        self.run_prepare()
        job = self.submitted[0]
        self.value['stages'] = {}
        self.latest = dict(job_id=job, status='running')
        def observe(p, j):
            self.value['status'] = 'canceled'
            return dict(status='running')
        self.manager.get = observe
        self.assertFalse(prepare(self.driver, lambda:self.value, self.write,
            lambda:self.value.get('status') == 'canceled', self.info))
        self.manager.cancel.assert_not_called()
        self.assertEqual(self.submitted, [job])
