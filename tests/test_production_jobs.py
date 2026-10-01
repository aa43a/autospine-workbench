"""Exercise recovery at dispatch boundaries and independent visual acceptance."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Thread
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

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

    def select_body(self,request,parent_job,registration):
        return dict(request,body_selection={'parent_job_id':parent_job,'registration_sha256':registration,'lineage':[{'artifact_sha256':'body'}]})

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
            if not self.manager.is_active(run_id):
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

    def test_live_execution_is_not_inferred_from_journal_or_persisted_in_it(self):
        value = self.manager.journal.create(self.request)
        value['status'] = 'running'
        value = self.manager.journal.append(value, 'execution_started')
        self.assertFalse(self.manager.execution_view(value)['execution_active'])
        with self.manager._active_lock:
            self.manager._active.add(value['run_id'])
        self.assertTrue(self.manager.execution_view(value)['execution_active'])
        self.assertNotIn('execution_active', self.manager.get(value['run_id']))
        self.manager._stop.set()
        self.assertFalse(self.manager.execution_view(value)['execution_active'])
        self.assertEqual(self.manager.journal.read(value['run_id']), value)
        with self.manager._active_lock:
            self.manager._active.clear()

    def test_status_reads_finish_while_joint_submission_is_blocked(self):
        from autospine_workbench.automation.production_routes import dispatch_production
        entered, release = Event(), Event()
        original_submit = self.driver.submit

        def blocked_submit(stage, run, job):
            if stage == 'joint':
                entered.set()
                if not release.wait(3):
                    raise RuntimeError('test submission was not released')
            return original_submit(stage, run, job)

        self.driver.submit = blocked_submit
        readers = ThreadPoolExecutor(max_workers=6)

        def read_route(tail):
            handler = SimpleNamespace(headers={}, server=object(),
                                      _send_visual_json=Mock(), _send_bytes=Mock())
            self.assertTrue(dispatch_production(['api', 'production', *tail], handler, 'GET'))
            return handler._send_visual_json.call_args.args

        try:
            run_id = self.manager.submit(self.request)['run_id']
            self.assertTrue(entered.wait(2))
            with patch('autospine_workbench.automation.production_routes.manager_for',
                       return_value=self.manager):
                futures = [
                    readers.submit(self.manager.get, run_id),
                    readers.submit(self.manager.list),
                    readers.submit(lambda: self.manager.execution_view(self.manager.get(run_id))),
                    readers.submit(self.manager.is_active, run_id),
                    readers.submit(read_route, [run_id]),
                    readers.submit(read_route, []),
                ]
                snapshot, rows, view, active, single_route, list_route = [
                    future.result(timeout=.5) for future in futures]
            self.assertFalse(release.is_set())
            self.assertEqual(snapshot['event'], 'joint_reserved')
            self.assertEqual(snapshot['stages']['joint']['status'], 'pending')
            self.assertEqual(rows, [snapshot])
            self.assertTrue(active)
            self.assertTrue(view['execution_active'])
            self.assertNotIn('execution_active', snapshot)
            self.assertEqual(snapshot['authority'], 'none')
            self.assertFalse(snapshot['production_authorized'])
            self.assertEqual(snapshot['stages']['review']['status'], 'pending')
            self.assertEqual(single_route, (200, view))
            self.assertEqual(list_route, (200, dict(runs=[view])))
            view['stages']['joint']['status'] = 'accepted'
            self.assertEqual(self.manager.get(run_id), snapshot)
        finally:
            release.set()
            readers.shutdown(wait=True)
        original = self.wait(run_id)
        self.assertEqual(original['status'], 'needs_review')
        self.assertEqual([stage for stage, _ in self.driver.calls], ['body', 'joint'])
        revised = self.wait(self.manager.revise(run_id, original['revision'],
                            {'hair': {'enabled': True}})['run_id'])
        self.assertEqual(revised['status'], 'needs_review')
        self.assertFalse(revised['production_authorized'])
        self.assertEqual(revised['stages']['body']['job_id'], original['stages']['body']['job_id'])
        self.assertNotEqual(revised['stages']['joint']['job_id'], original['stages']['joint']['job_id'])
        self.assertEqual([stage for stage, _ in self.driver.calls], ['body', 'joint', 'joint'])
        self.assertEqual(self.manager.get(run_id), original)

    def test_cancel_waits_for_dispatch_then_stops_the_reserved_child(self):
        entered, release, cancel_started, cancel_finished = Event(), Event(), Event(), Event()
        original_submit, original_write = self.driver.submit, self.manager._write
        failures = []

        def blocked_submit(stage, run, job):
            entered.set()
            if not release.wait(3):
                raise RuntimeError('test submission was not released')
            return original_submit(stage, run, job)

        def observing_after_cancel(run_id, change, event):
            if event == 'body_observing' and not cancel_finished.wait(2):
                raise RuntimeError('test cancellation did not finish')
            return original_write(run_id, change, event)

        self.driver.submit = blocked_submit
        self.manager._write = observing_after_cancel
        canceler = None
        try:
            run_id = self.manager.submit(self.request)['run_id']
            self.assertTrue(entered.wait(2))
            reserved = self.manager.get(run_id)

            def cancel():
                cancel_started.set()
                try:
                    self.manager.cancel(run_id, reserved['revision'])
                except BaseException as exc:
                    failures.append(exc)
                finally:
                    cancel_finished.set()

            canceler = Thread(target=cancel)
            canceler.start()
            self.assertTrue(cancel_started.wait(1))
            self.assertFalse(cancel_finished.wait(.05))
            self.assertEqual(self.manager.get(run_id), reserved)
        finally:
            release.set()
            if canceler is not None:
                canceler.join(2)
        self.assertTrue(cancel_finished.is_set())
        self.assertEqual(failures, [])
        result = self.wait(run_id)
        self.assertEqual(result['status'], 'canceled')
        self.assertEqual([stage for stage, _ in self.driver.calls], ['body'])
        self.assertEqual(self.driver.jobs[reserved['stages']['body']['job_id']]['status'], 'canceled')
        with self.assertRaisesRegex(PipelineRunError, 'production_revision_conflict'):
            self.manager.cancel(run_id, reserved['revision'])
        with self.assertRaisesRegex(PipelineRunError, 'production_canceled'):
            self.manager.resume(run_id, result['revision'])

    def test_close_keeps_status_reads_available_and_prevents_following_dispatch(self):
        entered, release, close_finished = Event(), Event(), Event()
        original_submit = self.driver.submit

        def blocked_submit(stage, run, job):
            entered.set()
            if not release.wait(3):
                raise RuntimeError('test submission was not released')
            return original_submit(stage, run, job)

        self.driver.submit = blocked_submit
        closer = None
        try:
            run_id = self.manager.submit(self.request)['run_id']
            self.assertTrue(entered.wait(2))

            def close():
                try:
                    self.manager.close()
                finally:
                    close_finished.set()

            closer = Thread(target=close)
            closer.start()
            self.assertTrue(self.manager._stop.wait(1))
            self.assertFalse(close_finished.is_set())
            snapshot = self.manager.get(run_id)
            self.assertEqual(self.manager.list(), [snapshot])
            self.assertTrue(self.manager.is_active(run_id))
            self.assertFalse(self.manager.execution_view(snapshot)['execution_active'])
        finally:
            release.set()
            if closer is not None:
                closer.join(2)
        self.assertTrue(close_finished.is_set())
        self.assertFalse(self.manager.is_active(run_id))
        self.assertEqual([stage for stage, _ in self.driver.calls], ['body'])
        self.assertEqual(self.manager.get(run_id)['event'], 'body_reserved')
        with self.assertRaisesRegex(PipelineRunError, 'pipeline_manager_closed'):
            self.manager.submit(self.request)

    def test_cancel_preserves_shared_sleeve_dependency(self):
        for shared in (True, False):
            value = self.manager.journal.create(self.request)
            job = 'job-' + ('a' if shared else 'b') * 32
            value['stages']['sleeves'] = dict(status='running',job_id=job,shared=shared,attempts=[])
            value = self.manager.journal.append(value, 'sleeves_reserved')
            self.driver.jobs[job] = dict(status='running')
            self.manager.cancel(value['run_id'], value['revision'])
            self.assertEqual(self.driver.jobs[job]['status'], 'running' if shared else 'canceled')

    def test_retry_retains_failed_sleeve_attempt_and_clears_its_reservation(self):
        value = self.manager.journal.create(self.request)
        for stage in ('source','bindings'):
            value['stages'][stage]['status'] = 'succeeded'
        job = 'job-' + 'c' * 32
        value['stages']['sleeves'] = dict(status='running',job_id=job,attempts=[dict(job_id=job)])
        value['status'] = 'blocked'
        value = self.manager.journal.append(value, 'failed')
        self.driver.jobs[job] = dict(status='blocked')
        with patch.object(self.manager, '_schedule'):
            result = self.manager.retry(value['run_id'], value['revision'])
        self.assertNotIn('job_id', result['stages']['sleeves'])
        self.assertEqual(result['stages']['sleeves']['attempts'], [dict(job_id=job)])

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

    def test_repair_revision_preserves_body_and_resets_joint_acceptance(self):
        from autospine_workbench.automation.production_revision import plan
        original=self.wait(self.manager.submit(self.request)['run_id'])
        preview=plan(self.manager,original['run_id'],original['revision'],body_registration='a'*64)
        revised=self.wait(self.manager.revise(original['run_id'],original['revision'],
            body_registration='a'*64,expected_plan_sha256=preview['plan_sha256'])['run_id'])
        self.assertEqual(revised['request']['body_selection']['parent_job_id'],original['stages']['body']['job_id'])
        self.assertEqual(revised['stages']['body'],original['stages']['body'])
        self.assertNotEqual(revised['stages']['joint']['job_id'],original['stages']['joint']['job_id'])
        self.assertEqual(revised['status'],'needs_review')
        reverted=plan(self.manager,revised['run_id'],revised['revision'],body_registration='')
        self.assertNotIn('body_selection',reverted['request'])
        with self.assertRaisesRegex(PipelineRunError,'unchanged_body'):
            plan(self.manager,original['run_id'],original['revision'],body_options={'yaw':20},body_registration='a'*64)
        self.manager.close()
        self.manager=ProductionJobs(Path(self.tmp.name)/'runs',self.driver,poll_seconds=.01)
        restored=self.manager.get(revised['run_id'])
        self.assertEqual(restored['request'],revised['request'])
        calls=len(self.driver.calls)
        self.manager.resume(restored['run_id'],restored['revision'])
        self.wait(restored['run_id'])
        self.assertEqual(len(self.driver.calls),calls)

    def test_existing_body_recovery_never_dispatches_body_again(self):
        from autospine_workbench.automation.production_existing_body import submit
        body={'job_id':'motion-'+'c'*32,'status':'succeeded','artifact_sha256':'body','attempts':[]}
        self.driver.jobs[body['job_id']]={'status':'succeeded','result':{'artifact_sha256':'body'}}
        with patch('autospine_workbench.automation.production_existing_body.prepare',return_value=(self.request,body)):
            original=self.wait(submit(self.manager,{})['run_id'])
            repeated=self.wait(submit(self.manager,{})['run_id'])
        self.assertEqual(original['run_id'],repeated['run_id'])
        self.assertEqual([s for s,_ in self.driver.calls],['joint'])
        self.assertEqual(repeated['status'],'needs_review')

    def test_direct_journal_create_is_not_visible_before_its_first_revision(self):
        from autospine_workbench.automation.production_journal import publish_document
        entered, release, list_started = Event(), Event(), Event()
        workers = ThreadPoolExecutor(max_workers=2)

        def held_publish(*args, **kwargs):
            entered.set()
            if not release.wait(3):
                raise RuntimeError('test publication was not released')
            return publish_document(*args, **kwargs)

        def list_runs():
            list_started.set()
            return self.manager.list()

        try:
            with patch('autospine_workbench.automation.production_journal.publish_document',
                       side_effect=held_publish):
                created = workers.submit(self.manager.journal.create, self.request)
                self.assertTrue(entered.wait(2))
                listing = workers.submit(list_runs)
                self.assertTrue(list_started.wait(1))
                time.sleep(.05)
                self.assertFalse(listing.done())
                release.set()
                value = created.result(timeout=1)
                self.assertEqual(listing.result(timeout=1), [value])
        finally:
            release.set()
            workers.shutdown(wait=True)
        self.assertEqual(value['revision'], 1)
        self.assertEqual(value['authority'], 'none')
        self.assertFalse(value['production_authorized'])

    def test_direct_journal_appends_keep_optimistic_revision_conflicts(self):
        value = self.manager.journal.create(self.request)
        workers = ThreadPoolExecutor(max_workers=2)
        try:
            attempts = [workers.submit(self.manager.journal.append, value, event)
                        for event in ('first_update', 'second_update')]
            results, errors = [], []
            for attempt in attempts:
                try:
                    results.append(attempt.result(timeout=1))
                except PipelineRunError as exc:
                    errors.append(exc.reason_code)
        finally:
            workers.shutdown(wait=True)
        self.assertEqual(len(results), 1)
        self.assertEqual(errors, ['production_revision_conflict'])
        self.assertEqual(results[0]['revision'], value['revision'] + 1)
        self.assertEqual(self.manager.get(value['run_id']), results[0])
        self.assertEqual(value['revision'], 1)
        self.assertEqual(value['event'], 'created')
        self.assertFalse(results[0]['production_authorized'])


if __name__ == '__main__':
    unittest.main()
