"""Real MotionIR intake, conservative unsupported skeletons and durable recovery."""
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import tempfile
import subprocess
import sys
from threading import Event
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from autospine_workbench.automation.motion_intake_jobs import MotionIntakeJobs, MAX_UPLOAD
from autospine_workbench.automation.motion_intake_worker import compile_source, execute
from autospine_workbench.automation.pipeline_run import PipelineRunError
from autospine_workbench.automation.storage_io import publish_document
from test_mixamo_map import source


class MotionIntakeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.projects = SimpleNamespace(state_root=self.root / 'state')
        self.jobs = MotionIntakeJobs(self.projects)
        self.addCleanup(self.jobs.close)

    def wait(self, job):
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            result = self.jobs.get(job['job_id'])
            if result['status'] not in ('pending', 'running'):
                return result
            time.sleep(.02)
        self.fail('motion worker did not finish')

    def test_real_worker_compiles_and_restart_reads_identical_receipt(self):
        raw = source('mixamorig:')
        queued = self.jobs.upload(BytesIO(raw), len(raw), '行走.bvh', 'front')
        done = self.wait(queued)
        self.assertEqual(done['status'], 'succeeded', done)
        self.assertEqual(done['result']['motion_status'], 'compiled', done)
        self.assertEqual(done['source_sha256'], sha256(raw).hexdigest())
        self.assertEqual(done['result']['character_animation_status'], 'not_built')
        preview = json.loads(self.jobs.preview(queued['job_id']))
        self.assertEqual(len(preview['frames']), 2)
        self.assertEqual(preview['frames'][1]['time'], .5)
        restarted = MotionIntakeJobs(self.projects)
        self.addCleanup(restarted.close)
        self.assertEqual(restarted.get(queued['job_id']), done)
        folder = self.jobs.folder(queued['job_id'])
        before = (folder / 'result.json').read_bytes()
        again = self.wait(self.jobs.retry(queued['job_id']))
        self.assertEqual(again['status'], 'succeeded', again)
        self.assertNotEqual(again['job_id'], queued['job_id'])
        self.assertEqual((folder / 'result.json').read_bytes(), before)

    def test_unknown_skeleton_keeps_preview_without_fabricating_mapping(self):
        raw = source('unknown:')
        folder = self.root / 'unknown'
        folder.mkdir()
        (folder / 'source.bvh').write_bytes(raw)
        result = compile_source(raw, 'side', folder, self.projects.state_root)
        self.assertEqual(result['motion_status'], 'needs_mapping')
        self.assertNotIn('motion', result)
        preview = json.loads((folder / 'preview.json').read_bytes())
        self.assertTrue(preview['names'][0].startswith('unknown:'))
        self.assertEqual(preview['view'], 'side')

    def test_invalid_inputs_never_start_worker(self):
        raw = source()
        with patch.object(self.jobs._pool, 'submit') as submit:
            for name, size, view in [('../a.bvh', len(raw), 'front'),
                                     ('a.npz', len(raw), 'front'),
                                     ('a.bvh', MAX_UPLOAD + 1, 'front'),
                                     ('a.bvh', len(raw), 'guess')]:
                with self.assertRaises(PipelineRunError):
                    self.jobs.upload(BytesIO(raw), size, name, view)
            with self.assertRaisesRegex(PipelineRunError, 'motion_upload_incomplete'):
                self.jobs.upload(BytesIO(raw), len(raw) + 1, 'short.bvh', 'front')
            submit.assert_not_called()

    def test_restart_interruption_retry_checks_source_identity(self):
        job = 'motion-' + 'a' * 32
        folder = self.jobs.folder(job, True)
        raw = source()
        request = dict(job_id=job, name='a.bvh', format='bvh', view='front',
                       source_sha256=sha256(raw).hexdigest(), byte_length=len(raw))
        publish_document(folder / 'request.json', request, staging=folder / 'staging')
        (folder / 'source.bvh').write_bytes(raw)
        self.assertEqual(self.jobs.get(job)['status'], 'interrupted')
        (folder / 'source.bvh').write_bytes(b'changed')
        with self.assertRaisesRegex(PipelineRunError, 'motion_source_changed'):
            self.jobs.retry(job)
        with self.assertRaisesRegex(ValueError, 'motion_source_changed'):
            execute(folder, self.projects.state_root, '')

    def test_malformed_source_fails_and_preview_tampering_is_detected(self):
        bad = b'not a bvh file at all'
        failed = self.wait(self.jobs.upload(BytesIO(bad), len(bad), 'bad.bvh', 'front'))
        self.assertEqual(failed['status'], 'failed')
        raw = source()
        done = self.wait(self.jobs.upload(BytesIO(raw), len(raw), 'ok.bvh', 'front'))
        self.assertEqual(done['status'], 'succeeded', done)
        (self.jobs.folder(done['job_id']) / 'preview.json').write_bytes(b'{}')
        with self.assertRaisesRegex(PipelineRunError, 'motion_preview_changed'):
            self.jobs.preview(done['job_id'])

    def test_missing_blender_has_actionable_failure(self):
        self.jobs.blender = ''
        raw = b'placeholder fbx source'
        result = self.wait(self.jobs.upload(BytesIO(raw), len(raw), 'a.fbx', 'front'))
        self.assertEqual(result['reason_code'], 'motion_blender_unavailable')

    def test_cancel_terminates_real_worker_and_persists_terminal_status(self):
        started = Event()
        original = subprocess.Popen
        children = []
        def launch(*args, **kwargs):
            if args[0][0] != sys.executable:
                return original(*args, **kwargs)
            child = original([sys.executable, '-c', 'import time; time.sleep(60)'], **kwargs)
            children.append(child)
            started.set()
            return child
        raw = source()
        with patch('autospine_workbench.automation.motion_intake_jobs.subprocess.Popen', side_effect=launch):
            queued = self.jobs.upload(BytesIO(raw), len(raw), 'slow.bvh', 'front')
            self.assertTrue(started.wait(5))
            self.jobs.cancel(queued['job_id'])
            done = self.wait(queued)
            self.jobs._pool.shutdown(wait=True)
        self.assertEqual(done['status'], 'canceled', done)
        self.assertIsNotNone(children[0].poll())
        persisted = json.loads((self.jobs.folder(queued['job_id']) / 'result.json').read_bytes())
        self.assertEqual(persisted['status'], 'canceled')


if __name__ == '__main__':
    unittest.main()
