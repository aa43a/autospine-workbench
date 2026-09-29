from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest

from autospine_workbench.automation.production_jobs import ProductionJobs
from autospine_workbench.automation.production_batch import ProductionBatches
from autospine_workbench.automation.pipeline_run import PipelineRunError
from test_production_jobs import Driver


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.driver = Driver()
        self.production = ProductionJobs(Path(self.tmp.name) / 'production', self.driver, poll_seconds=.01)
        self.batches = ProductionBatches(self.production, poll_seconds=.01)
        # Simulate source freezing performed by the real driver.
        self.driver.freeze = lambda value: dict(value, character_sha256='sha')
        self.body = dict(characters=[dict(project_id='a', character_job_id='char-a'),
                                     dict(project_id='b', character_job_id='char-b')],
                         source_job_ids=['source-a', 'source-b'], body_options={}, joint_config={})

    def tearDown(self):
        self.batches.close()
        self.production.close()
        self.tmp.cleanup()

    def wait(self, batch):
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline:
            with self.batches._lock:
                if batch not in self.batches._active:
                    return self.batches.get(batch)
            time.sleep(.01)
        self.fail('batch did not finish')

    def test_matrix_reserved_and_replayed_without_duplicate_jobs(self):
        value = self.wait(self.batches.submit(self.body)['batch_id'])
        self.assertEqual(value['status'], 'needs_review')
        self.assertEqual(len(value['cells']), 4)
        self.assertEqual(len({r['run_id'] for r in value['cells']}), 4)
        self.assertEqual(len(self.driver.calls), 8)
        self.batches.resume(value['batch_id'], value['revision'])
        replay = self.wait(value['batch_id'])
        self.assertEqual(len(self.driver.calls), 8)
        self.assertEqual(self.batches.submit(self.body)['batch_id'], value['batch_id'])
        self.assertFalse(replay['production_authorized'])

    def test_failed_cell_does_not_prevent_other_characters(self):
        original = self.driver.submit
        def submit(stage, run, job):
            if run['request']['project_id'] == 'a':
                raise PipelineRunError('test_bad_character')
            return original(stage, run, job)
        self.driver.submit = submit
        value = self.wait(self.batches.submit(self.body)['batch_id'])
        self.assertEqual(value['status'], 'needs_intervention')
        self.assertEqual([r['status'] for r in value['cells']],
                         ['blocked', 'blocked', 'needs_review', 'needs_review'])

    def test_reuse_exact_existing_candidate_without_inventing_acceptance(self):
        request = self.driver.freeze(dict(self.body['characters'][0], source_job_id='source-a',
                                         body_options={}, joint_config={}))
        run = self.production.ensure_reserved(request, 'production-' + '1' * 32)
        value = self.wait(self.batches.submit(self.body)['batch_id'])
        self.assertEqual(value['cells'][0]['run_id'], run['run_id'])
        self.assertTrue(value['cells'][0]['reused'])
        self.assertEqual(value['status'], 'needs_review')

    def test_duplicate_and_oversized_matrix_rejected_before_dispatch(self):
        self.body['source_job_ids'] = ['source-a', 'source-a']
        with self.assertRaises(PipelineRunError):
            self.batches.submit(self.body)
        self.body['source_job_ids'] = [str(i) for i in range(17)]
        with self.assertRaises(PipelineRunError):
            self.batches.submit(self.body)
        self.assertEqual(self.driver.calls, [])

    def test_sync_reads_new_stage_review_without_rebuilding(self):
        value = self.wait(self.batches.submit(self.body)['batch_id'])
        self.driver.accepted = True
        self.batches.resume(value['batch_id'], value['revision'])
        accepted = self.wait(value['batch_id'])
        self.assertEqual(accepted['status'], 'stage_accepted')
        self.assertEqual(len(self.driver.calls), 8)

    def test_reserved_run_conflict_cannot_replace_original_request(self):
        run_id = 'production-' + '2' * 32
        first = dict(character_job_id='one', character_sha256='sha')
        self.production.ensure_reserved(first, run_id)
        with self.assertRaisesRegex(PipelineRunError, 'production_reserved_request_conflict'):
            self.production.ensure_reserved(dict(first, character_job_id='other'), run_id)
