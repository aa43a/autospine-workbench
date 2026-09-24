import copy
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from autospine_workbench.automation import motion_repair_draft as draft
from autospine_workbench.resolved_project import canonical_sha256


class RepairDraftTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.manager = SimpleNamespace(_lock=threading.RLock(), folder=lambda _: Path(self.temp.name))
        self.report = dict(artifact_sha256='a'*64, rows=[dict(slot='arm', animation='reach',
                          details=[dict(triangle=3, time=0.5, texture_uv=[[0, 0], [1, 0], [0, 1]])])])
        self.patcher = patch.object(draft, 'evidence', side_effect=lambda *_:
                                    (copy.deepcopy(self.report), canonical_sha256(self.report)))
        self.patcher.start(); self.addCleanup(self.patcher.stop)

    def body(self, **changes):
        state = draft.inspect(self.manager, 'job')
        return dict(artifact_sha256=state['artifact_sha256'], evidence_sha256=state['evidence_sha256'],
                    expected_revision=state['revision'], action='partition', notes='check seam',
                    slot='arm', animation='reach', triangle=3, time=0.5, **changes)

    def test_view_needs_save_restore_and_scope_validation(self):
        body=self.body();body.update(action='pose_attachment',view_needs=['side','back'])
        state=draft.save(self.manager,'job',body)
        self.assertEqual(state['history'][-1]['view_needs'],['back','side'])
        self.assertEqual(draft.inspect(self.manager,'job')['history'][-1]['view_needs'],['back','side'])
        for views in ([],['side','side'],['unknown']):
            body=self.body();body.update(action='pose_attachment',view_needs=views)
            with self.assertRaisesRegex(RuntimeError,'view_needs_invalid'):draft.save(self.manager,'job',body)
        body=self.body();body['view_needs']=['side']
        with self.assertRaisesRegex(RuntimeError,'view_needs_invalid'):draft.save(self.manager,'job',body)

    def test_save_restore_withdraw_preserves_evidence(self):
        first = draft.save(self.manager, 'job', self.body())
        self.assertFalse(first['repair_executed'])
        self.assertEqual(first['history'][0]['event'], self.report['rows'][0]['details'][0])
        restored = SimpleNamespace(_lock=threading.RLock(), folder=self.manager.folder)
        self.assertEqual(draft.inspect(restored, 'job')['revision'], 1)
        body = self.body(); body['action'] = 'withdraw'
        last = draft.save(restored, 'job', body)
        self.assertEqual([r['action'] for r in last['history']], ['partition', 'withdraw'])
        self.assertFalse((Path(self.temp.name)/'stage-reviews').exists())

    def test_stale_revision_and_evidence(self):
        body = self.body(); draft.save(self.manager, 'job', body)
        with self.assertRaisesRegex(RuntimeError, 'revision_changed'):
            draft.save(self.manager, 'job', body)
        body = self.body(); self.report['artifact_sha256'] = 'b'*64
        with self.assertRaisesRegex(RuntimeError, 'evidence_changed'):
            draft.save(self.manager, 'job', body)

    def test_fabricated_event_and_invalid_action_rejected(self):
        for field, value in [('triangle', 999), ('time', 0.6), ('slot', 'other'), ('animation', 'walk'), ('action', 'accepted')]:
            body = self.body(); body[field] = value
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                draft.save(self.manager, 'job', body)
        self.assertEqual(draft.inspect(self.manager, 'job')['revision'], 0)

    def test_tampered_chain_rejected(self):
        draft.save(self.manager, 'job', self.body())
        path = Path(self.temp.name)/'repair-drafts/draft-0001.json'
        import json
        row=json.loads(path.read_text()); row['previous_sha256']='bad'
        path.write_text(json.dumps(row))
        with self.assertRaisesRegex(RuntimeError, 'history_invalid|storage_invalid'):
            draft.inspect(self.manager, 'job')

    def test_route_methods(self):
        from autospine_workbench.automation.motion_intake_routes import _methods
        self.assertEqual(_methods(['job', 'repair-draft']), 'GET, HEAD, POST, OPTIONS')

    def test_evidence_read_does_not_block_job_lock(self):
        entered = threading.Event(); release = threading.Event(); errors = []
        def slow(*_):
            entered.set(); release.wait(5)
            return self.report, canonical_sha256(self.report)
        def work():
            try: draft.inspect(self.manager, 'job')
            except Exception as error: errors.append(error)
        with patch.object(draft, 'evidence', side_effect=slow):
            thread = threading.Thread(target=work); thread.start()
            try:
                self.assertTrue(entered.wait(2))
                acquired = self.manager._lock.acquire(timeout=0.2)
                self.assertTrue(acquired)
                if acquired: self.manager._lock.release()
            finally: release.set(); thread.join(5)
        self.assertFalse(errors)
