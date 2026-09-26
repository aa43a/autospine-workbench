"""Real immutable fixtures exercise separate review journals and portable exports."""
from io import BytesIO
import json
from threading import Barrier, Event, Thread
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from test_motion_related_player_loading import RelatedPlayerLoadingTests as Fixture
from autospine_workbench.automation import motion_related_review as review
from autospine_workbench.automation import motion_related_candidates as related
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.motion_related_export import package
from autospine_workbench.automation.storage_io import canonical_bytes


class RelatedReviewTests(unittest.TestCase):
    setUp = Fixture.setUp

    def body(self, decision='accepted_with_exceptions'):
        state = review.inspect(self.manager, 'job', self.digest)
        return dict(registration_sha256=self.digest, artifact_sha256=self.candidate,
                    evidence_sha256=state['evidence_sha256'], expected_revision=state['revision'],
                    decision=decision, notes='仅接受当前动作范围，保留未测遮挡')

    def test_append_reload_revoke_and_export_without_changing_baseline_or_candidate(self):
        root = self.folder / 'stage-reviews'; root.mkdir()
        baseline = root / 'review-0001.json'; baseline.write_bytes(b'original baseline')
        store = AnimatedStore(self.root); original = store.read(self.candidate)
        before = review.inspect(self.manager, 'job', self.digest)
        self.assertIsNone(before['current']); self.assertEqual(before['imported_visual'], self.f.visual)
        accepted = review.save(self.manager, 'job', self.digest, self.body())
        self.assertTrue(accepted['current_applies'])
        self.assertEqual(accepted['readiness']['status'], 'evidence_incomplete')
        self.assertEqual(accepted['readiness'], before['readiness'])
        self.assertEqual(review.inspect(self.manager, 'job', self.digest), accepted)
        revoked = review.save(self.manager, 'job', self.digest, self.body('revoked'))
        self.assertEqual(revoked['history'][0], accepted['current'])
        self.assertEqual(revoked['revision'], 2)
        self.assertEqual(store.read(self.candidate), original)
        self.assertEqual(baseline.read_bytes(), b'original baseline')
        raw, _ = related.read(self.manager, 'job', ['related-candidates', self.digest, 'candidate.zip'])
        with ZipFile(BytesIO(raw)) as archive:
            manifest = json.loads(archive.read('related-export.json'))
            self.assertEqual(manifest['registration_sha256'], self.digest)
            self.assertEqual(manifest['stage_review_revision'], 2)
            self.assertEqual(json.loads(archive.read('related-stage-review.json')), revoked)
            self.assertEqual({n: archive.read(n) for n in manifest['candidate_files']}, original)
            self.assertIn('related-stage-review.json', manifest['evidence_files'])
        rows = json.loads(related.read(self.manager, 'job', ['related-candidates.json'])[0])['rows']
        self.assertEqual(rows[0]['stage_review']['current']['decision'], 'revoked')
        self.assertEqual(rows[0]['visual'], self.f.visual)

    def test_new_receipt_same_candidate_has_no_inherited_review(self):
        body = self.body(); review.save(self.manager, 'job', self.digest, body)
        other = related.register(self.manager, 'job', self.f.files,
            dict(self.f.receipt, new_evidence_note='second registration'), self.f.runtime, self.f.visual)
        self.assertNotEqual(other, self.digest)
        state = review.inspect(self.manager, 'job', other)
        self.assertEqual(state['artifact_sha256'], self.candidate)
        self.assertEqual(state['revision'], 0); self.assertIsNone(state['current'])
        with self.assertRaisesRegex(RuntimeError, 'request_invalid'):
            review.save(self.manager, 'job', other, body)
        with self.assertRaisesRegex(RuntimeError, 'evidence_changed'):
            review.save(self.manager, 'job', other, dict(body, registration_sha256=other))

    def test_stale_revision_hash_and_plain_acceptance_cannot_be_saved(self):
        body = self.body()
        for change, error in [({'decision':'accepted'}, 'exceptions_require'),
                              ({'evidence_sha256':'wrong'}, 'evidence_changed'),
                              ({'artifact_sha256':'wrong'}, 'evidence_changed'),
                              ({'notes':' '}, 'request_invalid'),
                              ({'expected_revision':True}, 'request_invalid')]:
            with self.subTest(change=change), self.assertRaisesRegex(RuntimeError, error):
                review.save(self.manager, 'job', self.digest, dict(body, **change))
        review.save(self.manager, 'job', self.digest, body)
        with self.assertRaisesRegex(RuntimeError, 'revision_changed'):
            review.save(self.manager, 'job', self.digest, body)
        self.assertEqual(len(review.history(self.manager, 'job', self.digest)), 1)

    def test_evidence_change_requires_recheck_not_legacy_acceptance(self):
        review.save(self.manager, 'job', self.digest, self.body())
        original = review.readiness
        def upgraded(*args):
            report = original(*args); report['new_diagnostic'] = 'unmeasured'; return report
        with patch.object(review, 'readiness', side_effect=upgraded):
            self.assertFalse(review.inspect(self.manager, 'job', self.digest)['current_applies'])
        self.assertEqual(len(review.history(self.manager, 'job', self.digest)), 1)

    def test_history_cannot_be_transplanted_or_have_gaps(self):
        review.save(self.manager, 'job', self.digest, self.body())
        path = self.folder / 'related-stage-reviews' / self.digest / 'review-0001.json'
        original = path.read_bytes(); row = json.loads(original)
        row['registration_sha256'] = 'f' * 64; path.write_bytes(canonical_bytes(row))
        with self.assertRaisesRegex(RuntimeError, 'history_invalid'):
            review.inspect(self.manager, 'job', self.digest)
        path.write_bytes(original); path.rename(path.with_name('review-0002.json'))
        with self.assertRaisesRegex(RuntimeError, 'history_invalid'):
            review.inspect(self.manager, 'job', self.digest)

    def test_runtime_or_asset_corruption_cannot_be_reviewed(self):
        body = self.body(); store = AnimatedStore(self.root)
        (store.root / self.candidate / 'texture.png').write_bytes(b'changed')
        with self.assertRaisesRegex(RuntimeError, 'artifact_invalid'):
            review.save(self.manager, 'job', self.digest, body)
        self.assertFalse((self.folder / 'related-stage-reviews').exists())

    def test_slow_evidence_is_outside_lock_and_source_race_is_rejected(self):
        body = self.body(); started, release = Event(), Event(); errors = []
        original = related.load
        def slow(*args):
            value = original(*args); started.set()
            if not release.wait(5): raise RuntimeError('timeout')
            return value
        def save():
            try: review.save(self.manager, 'job', self.digest, body)
            except Exception as error: errors.append(error)
        with patch.object(related, 'load', side_effect=slow):
            thread = Thread(target=save); thread.start()
            try:
                self.assertTrue(started.wait(2))
                acquired = self.manager._lock.acquire(timeout=.2)
                self.assertTrue(acquired)
                if acquired:
                    self.manager.get = lambda _: dict(kind='adapt', status='succeeded',
                                                       result=dict(artifact_sha256='changed'))
                    self.manager._lock.release()
            finally: release.set(); thread.join(5)
        self.assertFalse(thread.is_alive()); self.assertEqual(len(errors), 1)
        self.assertIn('baseline_changed', str(errors[0]))
        self.assertFalse((self.folder / 'related-stage-reviews').exists())

    def test_export_rejects_review_of_other_candidate_or_evidence(self):
        value, files = related.load(self.manager, 'job', self.digest)
        state = review.inspect(self.manager, 'job', self.digest)
        for change in [dict(artifact_sha256='wrong'), dict(evidence_sha256='wrong')]:
            with self.assertRaisesRegex(ValueError, 'review_identity'):
                package(value, files, dict(state, **change))

    def test_two_simultaneous_saves_cannot_overwrite_each_other(self):
        body = self.body(); barrier = Barrier(2); results = []; errors = []
        original = related.load
        def synchronized(*args):
            loaded = original(*args); barrier.wait(timeout=5); return loaded
        def save():
            try: results.append(review.save(self.manager, 'job', self.digest, body))
            except Exception as error: errors.append(error)
        with patch.object(related, 'load', side_effect=synchronized):
            threads = [Thread(target=save) for _ in range(2)]
            for thread in threads: thread.start()
            for thread in threads: thread.join(6)
        self.assertTrue(all(not t.is_alive() for t in threads))
        self.assertEqual(len(results), 1); self.assertEqual(len(errors), 1)
        self.assertIn('revision_changed', str(errors[0]))
        self.assertEqual(len(review.history(self.manager, 'job', self.digest)), 1)


del Fixture
