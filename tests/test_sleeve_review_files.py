import hashlib
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from autospine_workbench.automation.sleeve_web_jobs import SleeveWebJobs
from autospine_workbench.automation.storage_io import publish_document


class SleeveReviewFileTests(unittest.TestCase):
    def test_ordinary_spine_timeline_is_exact_path_and_receipt_bound(self):
        from autospine_workbench.automation.sleeve_review_files import read
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); page=root/'spine/fixture/ordinary/index.html'
            page.parent.mkdir(parents=True); page.write_bytes(b'<h1>Ordinary timeline</h1>')
            (root/'receipts').mkdir()
            publish_document(root/'receipts/spine.json', dict(files={
                'fixture/ordinary/index.html':hashlib.sha256(page.read_bytes()).hexdigest(),
                'fixture/skeleton.json':hashlib.sha256(b'{}').hexdigest()}), staging=root/'.staging')
            report=dict(steps=[dict(id='spine',status='succeeded')])
            parts=['spine','fixture','ordinary','index.html']
            self.assertEqual(read(root,'fixture',report,parts),
                             (b'<h1>Ordinary timeline</h1>','text/html; charset=utf-8'))
            for invalid in (['spine','other','ordinary','index.html'], ['spine','fixture','skeleton.json'],
                            ['spine','fixture','ordinary','other.html'], ['spine','fixture','..','index.html'],
                            ['spine','fixture','ordinary','index.html','extra']):
                with self.subTest(parts=invalid),self.assertRaises(RuntimeError):read(root,'fixture',report,invalid)
            with self.assertRaisesRegex(RuntimeError,'not_ready'):
                read(root,'fixture',dict(steps=[dict(id='spine',status='running')]),parts)
            page.write_bytes(b'tampered')
            with self.assertRaisesRegex(RuntimeError,'cached_output_changed'):read(root,'fixture',report,parts)

    def test_byte_checked_review_is_project_scoped_and_withdrawable(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            store = SimpleNamespace(workspace_root=root, state_root=root/'state',
                get_project=lambda p: {'resolved': {'sha256': 'a'*64}})
            manager = SleeveWebJobs(store)
            try:
                draft = manager.drafts/'fixture/draft.json'
                draft.parent.mkdir(parents=True); draft.write_text('{}')
                with patch.object(manager._pool, 'submit'):
                    job = manager.submit('fixture', 'a'*64)
                job_id = job['job_id']; job_root = manager._path(job_id)
                run = manager.output/'fixture/run-test'
                page = run/'repair/fixture/index.html'
                page.parent.mkdir(parents=True); page.write_bytes(b'<h1>Review</h1>')
                (run/'receipts').mkdir()
                publish_document(run/'receipts/repair.json', dict(files={
                    'fixture/index.html': hashlib.sha256(page.read_bytes()).hexdigest()}), staging=run/'.staging')
                publish_document(job_root/'result-location.json', dict(directory=str(run)), staging=job_root/'.staging')
                manager._jobs[job_id].update(status='blocked', result=dict(steps=[
                    dict(id='repair', status='succeeded')]))
                parts = ['repair', 'fixture', 'index.html']
                self.assertEqual(manager.review_file('fixture', job_id, parts),
                                 (b'<h1>Review</h1>', 'text/html; charset=utf-8'))
                for invalid in (['repair', '..', 'index.html'], ['repair', 'other', 'index.html'],
                                ['repair', 'fixture', 'missing.png'], ['spine', 'fixture', 'index.html']):
                    with self.subTest(invalid=invalid), self.assertRaises(RuntimeError):
                        manager.review_file('fixture', job_id, invalid)
                with self.assertRaisesRegex(RuntimeError, 'not_found'):
                    manager.review_file('other', job_id, parts)
                page.write_bytes(b'changed')
                with self.assertRaisesRegex(RuntimeError, 'cached_output_changed'):
                    manager.review_file('fixture', job_id, parts)
                page.write_bytes(b'<h1>Review</h1>')
                (job_root/'visibility').mkdir()
                publish_document(job_root/'visibility/00000001.json',
                                 dict(revision=1, withdrawn=True), staging=job_root/'.staging')
                with self.assertRaisesRegex(RuntimeError, 'withdrawn'):
                    manager.review_file('fixture', job_id, parts)
            finally:
                manager.close()
