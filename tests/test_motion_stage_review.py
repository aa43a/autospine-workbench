"""Visual decisions retain revisions without laundering technical failures."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import RLock, Event, Thread
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from autospine_workbench.automation import motion_stage_review as review
from autospine_workbench.automation.motion_intake_routes import _methods
from autospine_workbench.resolved_project import canonical_sha256


class StageReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.manager = SimpleNamespace(_lock=RLock(), folder=lambda _: Path(self.temp.name))
        self.report = dict(artifact_sha256='candidate', status='needs_changes', stages=[
            dict(stage='Runtime', status='sampled_pass'), dict(stage='遮挡', status='needs_changes')])
        self.patch = patch.object(review, 'evidence', side_effect=lambda *_:
                                  (deepcopy(self.report), canonical_sha256(self.report)))
        self.patch.start(); self.addCleanup(self.patch.stop)

    def body(self, decision='accepted_with_exceptions', revision=0):
        return dict(artifact_sha256='candidate', evidence_sha256=canonical_sha256(self.report),
                    expected_revision=revision, decision=decision, notes='保留遮挡异常，限定待机范围')

    def test_append_revoke_restore_and_keep_checks(self):
        first = review.save(self.manager, 'job', self.body())
        self.assertEqual(first['readiness']['status'], 'needs_changes')
        self.assertFalse(first['production_authorized'])
        second = review.save(self.manager, 'job', self.body('revoked', 1))
        self.assertEqual(second['revision'], 2)
        self.assertEqual(second['history'][0], first['current'])
        restored = SimpleNamespace(_lock=RLock(), folder=self.manager.folder)
        self.assertEqual(review.inspect(restored, 'job'), second)

    def test_stale_revision_and_evidence_refused(self):
        review.save(self.manager, 'job', self.body())
        with self.assertRaisesRegex(RuntimeError, 'revision_changed'):
            review.save(self.manager, 'job', self.body())
        stale = self.body(revision=1)
        self.report['status'] = 'evidence_incomplete'
        self.assertFalse(review.inspect(self.manager, 'job')['current_applies'])
        with self.assertRaisesRegex(RuntimeError, 'evidence_changed'):
            review.save(self.manager, 'job', stale)
        self.assertEqual(len(review.history(self.manager, 'job')), 1)

    def test_exception_cannot_be_plain_acceptance(self):
        with self.assertRaisesRegex(RuntimeError, 'exceptions_require'):
            review.save(self.manager, 'job', self.body('accepted'))
        self.report['status'] = 'stage_review'
        self.assertEqual(review.save(self.manager, 'job', self.body('accepted'))['revision'], 1)

    def test_missing_runtime_and_blank_exception_notes_refused(self):
        body = self.body(); body['notes'] = '  '
        with self.assertRaisesRegex(RuntimeError, 'request_invalid'):
            review.save(self.manager, 'job', body)
        self.report['stages'][0]['status'] = 'unmeasured'
        with self.assertRaisesRegex(RuntimeError, 'runtime_required'):
            review.save(self.manager, 'job', self.body())

    def test_gap_or_changed_chain_is_not_silently_ignored(self):
        review.save(self.manager, 'job', self.body())
        root = Path(self.temp.name) / 'stage-reviews'
        (root / 'review-0001.json').rename(root / 'review-0002.json')
        with self.assertRaisesRegex(RuntimeError, 'history_invalid'):
            review.inspect(self.manager, 'job')

    def test_route_methods(self):
        self.assertEqual(_methods(['job', 'stage-review']), 'GET, HEAD, POST, OPTIONS')

    def test_slow_evidence_does_not_hold_job_manager_lock(self):
        for operation in ('read', 'write'):
            started, release = Event(), Event()
            errors = []
            def slow(*_):
                started.set()
                if not release.wait(5): raise RuntimeError('test_timeout')
                return deepcopy(self.report), canonical_sha256(self.report)
            def run():
                try:
                    if operation == 'read': review.inspect(self.manager, 'job')
                    else: review.save(self.manager, 'job', self.body())
                except Exception as exc: errors.append(exc)
            review.evidence.side_effect = slow
            worker = Thread(target=run); worker.start()
            try:
                self.assertTrue(started.wait(2))
                acquired = self.manager._lock.acquire(timeout=.2)
                if acquired: self.manager._lock.release()
                self.assertTrue(acquired, 'evidence I/O must not block unrelated job operations')
            finally:
                release.set(); worker.join(5)
            self.assertFalse(worker.is_alive())
            self.assertEqual(errors, [])


if __name__ == '__main__': unittest.main()
