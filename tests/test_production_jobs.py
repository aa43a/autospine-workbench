"""Exercise recovery at dispatch boundaries and independent visual acceptance."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
import time
import unittest

from autospine_workbench.automation.production_jobs import ProductionJobs
from autospine_workbench.automation.production_submission import child_id, reserved_child
from autospine_workbench.automation.pipeline_run import PipelineRunError


class Driver:
    def __init__(self):
        self.jobs = {}
        self.calls = []
        self.accepted = False
        self.changed = False

    def freeze(self, body):
        return deepcopy(body)

    def validate(self, request):
        if self.changed:
            raise PipelineRunError('production_source_changed')

    def revision_request(self, request, config=None, body_options=None):
        value = deepcopy(request)
        if config is not None:
            value['joint_config'] = config
        if body_options is not None:
            value['body_options'] = deepcopy(body_options)
        return value

    def exists(self, job):
        return job in self.jobs

    def submit(self, stage, run, job):
        self.calls.append((stage, job))
        self.jobs[job] = dict(job_id=job, status='succeeded', result={'artifact_sha256': stage})
        return self.jobs[job]

    def get(self, job):
        return self.jobs[job]

    def review(self, job):
        return dict(current_applies=self.accepted, current={'decision': 'accepted_with_exceptions'},
                    evidence_sha256='evidence', revision=int(self.accepted))

    def cancel(self, job):
        self.jobs[job]['status'] = 'canceled'


class ProductionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.driver = Driver()
        self.manager = ProductionJobs(Path(self.tmp.name) / 'runs', self.driver, poll_seconds=.01)
        self.request = dict(project_id='p',character_job_id='old-character', character_sha256='character')

    def tearDown(self):
        self.manager.close()
        self.tmp.cleanup()

    def wait(self, run_id):
        limit = time.monotonic() + 3
        while time.monotonic() < limit:
            with self.manager._lock:
                if run_id not in self.manager._active:
                    return self.manager.get(run_id)
            time.sleep(.01)
        self.fail('coordinator did not finish')

    def test_chain_does_not_inherit_character_or_body_acceptance(self):
        value = self.wait(self.manager.submit(self.request)['run_id'])
        self.assertEqual(value['status'], 'needs_review')
        self.assertFalse(value['production_authorized'])
        self.assertEqual([x[0] for x in self.driver.calls], ['body', 'joint'])
        self.driver.accepted = True
        self.manager.resume(value['run_id'], value['revision'])
        value = self.wait(value['run_id'])
        self.assertEqual(value['status'], 'stage_accepted')
        self.assertEqual(len(self.driver.calls), 2)

    def test_recover_published_child_without_double_submit(self):
        value = self.manager.journal.create(self.request)
        job = 'motion-' + 'a' * 32
        value['stages']['body'].update(status='pending', job_id=job)
        value = self.manager.journal.append(value, 'body_reserved')
        self.driver.jobs[job] = dict(job_id=job, status='succeeded', result={})
        self.manager.resume(value['run_id'], value['revision'])
        result = self.wait(value['run_id'])
        self.assertEqual(result['status'], 'needs_review')
        self.assertEqual([x[0] for x in self.driver.calls], ['joint'])

    def test_stale_source_stops_before_any_child(self):
        value = self.manager.journal.create(self.request)
        self.driver.changed = True
        with self.assertRaisesRegex(PipelineRunError, 'production_source_changed'):
            self.manager.resume(value['run_id'], value['revision'])
        self.assertFalse(self.driver.calls)

    def test_resume_clears_old_block_before_waiting_for_preparation(self):
        entered, release = Event(), Event()
        def prepare(read, write, stopped):
            entered.set()
            release.wait(2)
            return False
        self.driver.prepare = prepare
        value = self.manager.journal.create(self.request)
        value.update(status='blocked', reason_code='joint_review_required')
        value = self.manager.journal.append(value, 'blocked')
        try:
            self.manager.resume(value['run_id'], value['revision'])
            self.assertTrue(entered.wait(2))
            current = self.manager.get(value['run_id'])
            self.assertEqual(current['status'], 'running')
            self.assertNotIn('reason_code', current)
        finally:
            release.set()
        self.wait(value['run_id'])

    def test_revision_conflict_and_cancel_are_durable(self):
        value = self.manager.journal.create(self.request)
        with self.assertRaisesRegex(PipelineRunError, 'production_revision_conflict'):
            self.manager.cancel(value['run_id'], 0)
        result = self.manager.cancel(value['run_id'], value['revision'])
        with self.assertRaisesRegex(PipelineRunError, 'production_canceled'):
            self.manager.resume(result['run_id'], result['revision'])
        self.assertEqual(self.manager.journal.read(value['run_id'])['status'], 'canceled')

    def test_reservation_single_use_and_no_leak(self):
        job = 'motion-' + 'a' * 32
        with reserved_child(job):
            self.assertEqual(child_id('motion-'), job)
            with self.assertRaises(PipelineRunError):
                child_id('motion-')
        self.assertNotEqual(child_id('motion-'), job)

    def test_joint_revision_reuses_body_but_not_acceptance(self):
        original=self.wait(self.manager.submit(self.request)['run_id'])
        revised=self.manager.revise(original['run_id'],original['revision'],{'face':{'enabled':True}})
        revised=self.wait(revised['run_id'])
        self.assertEqual(revised['stages']['body']['job_id'],original['stages']['body']['job_id'])
        self.assertNotEqual(revised['stages']['joint']['job_id'],original['stages']['joint']['job_id'])
        self.assertEqual([stage for stage,_ in self.driver.calls],['body','joint','joint'])
        self.assertEqual(revised['status'],'needs_review')
        self.assertEqual(revised['stages']['source']['status'],'reused')
        self.assertEqual(revised['stages']['bindings']['status'],'reused')
        self.assertEqual(self.manager.get(original['run_id']),original)

    def test_body_parameter_change_preserves_character_but_rebuilds_dependent_steps(self):
        from autospine_workbench.automation.production_revision import plan
        original=self.wait(self.manager.submit(self.request)['run_id'])
        preview=plan(self.manager,original['run_id'],original['revision'],body_options={'projection':{'yaw':30}})
        self.assertIn('character',preview['reuse_stages']);self.assertNotIn('body',preview['reuse_stages'])
        self.assertFalse(preview['acceptance_inherited'])
        with self.assertRaisesRegex(PipelineRunError,'plan_changed'):
            self.manager.revise(original['run_id'],original['revision'],body_options={'projection':{'yaw':30}},expected_plan_sha256='bad')
        self.assertEqual(len(self.manager.list()),1)
        revised=self.manager.revise(original['run_id'],original['revision'],body_options={'projection':{'yaw':30}},expected_plan_sha256=preview['plan_sha256'])
        revised=self.wait(revised['run_id'])
        self.assertNotEqual(revised['stages']['body']['job_id'],original['stages']['body']['job_id'])
        self.assertEqual(revised['stages']['character'],original['stages']['character'])
        self.assertEqual(revised['status'],'needs_review')

    def test_source_change_after_preview_invalidates_plan_without_creating_run(self):
        from autospine_workbench.automation.production_revision import plan
        original=self.wait(self.manager.submit(self.request)['run_id'])
        preview=plan(self.manager,original['run_id'],original['revision'])
        before=self.driver.revision_request
        def changed(*args):
            return dict(before(*args),character_job_id='new-character',character_sha256='new-sha')
        self.driver.revision_request=changed
        with self.assertRaisesRegex(PipelineRunError,'plan_changed'):
            self.manager.revise(original['run_id'],original['revision'],expected_plan_sha256=preview['plan_sha256'])
        self.assertEqual(len(self.manager.list()),1)
        updated=plan(self.manager,original['run_id'],original['revision'])
        self.assertEqual(updated['reuse_stages'],[])
        self.assertEqual(updated['refresh_stages'],['source','bindings','character'])
        self.assertEqual(updated['rebuild_stages'],['body','joint'])
        self.assertIn('body',updated['rebuild_stages'])
        self.assertEqual(self.manager.get(original['run_id']),original)


if __name__ == '__main__':
    unittest.main()
