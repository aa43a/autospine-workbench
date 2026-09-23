"""Generation contracts and synthetic worker receipts, not model-quality evidence."""
from hashlib import sha256
from io import StringIO
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from autospine_workbench.automation.motion_generation_jobs import options, submit
from autospine_workbench.automation.motion_generation_provenance import REVISION, producer
from autospine_workbench.automation.motion_generation_worker import execute
from autospine_workbench.automation.motion_intake_jobs import MotionIntakeJobs
from autospine_workbench.automation.pipeline_run import PipelineRunError
from autospine_workbench.automation.storage_io import canonical_bytes, read_document
from autospine_workbench.motion_bundle_reader import VerifiedMotionBundleReader
from tests.fixtures.kimodo_npz_archive import build_npz, motion_member_bytes

BODY = dict(prompt='A person waves.', duration_seconds=4, seed=42, diffusion_steps=100, view='front')


class MotionGenerationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.jobs = MotionIntakeJobs(SimpleNamespace(state_root=self.root / 'state', workspace_root=self.root))
        self.addCleanup(self.jobs.close)

    def test_strict_request_cannot_supply_provenance_command_or_multiple_clips(self):
        for change in (dict(prompt=''), dict(prompt='One. Two.'), dict(prompt='.'),
                       dict(prompt='One\nTwo'), dict(duration_seconds=float('nan')),
                       dict(duration_seconds=True), dict(seed=-1), dict(seed=True),
                       dict(diffusion_steps=101), dict(command='anything'), dict(view='guess')):
            with self.subTest(change=change), self.assertRaises(PipelineRunError):
                options(dict(BODY, **change))
        self.assertEqual(options(BODY), BODY)

    def test_restart_retry_uses_new_job_and_preserves_original_request(self):
        with patch('autospine_workbench.automation.motion_generation_jobs.availability', return_value='configured'), \
                patch.object(self.jobs._pool, 'submit'):
            first = submit(self.jobs, BODY)
            folder = self.jobs.folder(first['job_id'])
            before = (folder / 'request.json').read_bytes()
            del self.jobs._jobs[first['job_id']]
            self.assertEqual(self.jobs.get(first['job_id'])['status'], 'interrupted')
            second = self.jobs.retry(first['job_id'])
            self.assertNotEqual(first['job_id'], second['job_id'])
            lineage = dict(job_id=first['job_id'], request_sha256=sha256(before).hexdigest())
            self.assertEqual(second['retry_of'], lineage)
            self.assertEqual(read_document(self.jobs.folder(second['job_id']) / 'request.json')['generation'], BODY)
            self.assertEqual(read_document(self.jobs.folder(second['job_id']) / 'request.json')['retry_of'], lineage)
            self.assertEqual((folder / 'request.json').read_bytes(), before)
            pending = self.jobs._jobs.pop(second['job_id'])
            self.assertEqual(self.jobs.get(second['job_id'])['retry_of'], lineage)
            self.jobs._jobs[second['job_id']] = pending
            self.jobs.cancel(second['job_id'])
            self.jobs._execute(second['job_id'])
            self.assertEqual(self.jobs.get(second['job_id'])['status'], 'canceled')
            del self.jobs._jobs[second['job_id']]
            self.assertEqual(self.jobs.get(second['job_id'])['retry_of'], lineage)

    def test_unconfigured_runtime_does_not_queue(self):
        with patch('autospine_workbench.automation.motion_generation_jobs.availability', return_value='unavailable'), \
                self.assertRaisesRegex(PipelineRunError, 'motion_generation_unavailable'):
            submit(self.jobs, BODY)
        self.assertFalse(self.jobs._jobs)

    def worker(self, environment_changed=False):
        folder = self.root / 'job'
        folder.mkdir()
        runtime = self.root / 'runtime'
        job = 'motion-' + 'a'*32
        request = dict(job_id=job, generation=BODY, view='front',
                       npz_options=dict(profile='kimodo-soma77-v1', fps='30'))
        (folder / 'request.json').write_bytes(canonical_bytes(request))
        raw = build_npz(motion_member_bytes())
        environment = dict(repository_revision=REVISION, test_fixture=True)
        def launch(command, **kwargs):
            self.assertIsInstance(command, list)
            self.assertFalse(kwargs.get('shell', False))
            self.assertIn('kimodo.scripts.generate', command)
            self.assertEqual(kwargs['env']['HF_HUB_OFFLINE'], '1')
            (folder / 'generated/motion.npz').write_bytes(raw)
            class Child:
                stdout = StringIO('Starting the pinned Kimodo pilot with verified files.\n')
                def __enter__(self): return self
                def __exit__(self, *args): pass
                def wait(self): return 0
            return Child()
        after = dict(environment, changed=True) if environment_changed else environment
        with patch('autospine_workbench.automation.motion_generation_worker.inspect', side_effect=[environment, after]), \
                patch('autospine_workbench.automation.motion_generation_worker.prepare', return_value=folder / 'text-encoders'), \
                patch('autospine_workbench.automation.motion_generation_worker.verify'), \
                patch('autospine_workbench.automation.motion_generation_worker.subprocess.run', return_value=SimpleNamespace(returncode=0)), \
                patch('autospine_workbench.automation.motion_generation_worker.subprocess.Popen', side_effect=launch):
            execute(folder, self.jobs.state_root, runtime)
        return folder, raw, environment

    def test_worker_compiles_exact_npz_with_recorded_server_provenance(self):
        folder, raw, environment = self.worker()
        result = read_document(folder / 'worker-result.json')
        self.assertEqual(result['source_sha256'], sha256(raw).hexdigest())
        self.assertEqual(result['producer_status'], 'recorded')
        self.assertEqual(result['motion_status'], 'compiled')
        bundle = VerifiedMotionBundleReader(self.jobs.state_root).load(
            result['motion']['clip_sha256'], result['motion']['bundle_sha256'])
        self.assertEqual(bundle.raw_npz, raw)
        self.assertEqual(bundle.kimodo_source['producer'], producer(environment, read_document(folder / 'generation-request.json')))
        self.assertEqual(result['generation']['parameters'], BODY)

    def test_environment_change_never_publishes_a_success_receipt(self):
        with self.assertRaisesRegex(ValueError, 'motion_generation_environment_changed'):
            self.worker(environment_changed=True)
        self.assertFalse((self.root / 'job/worker-result.json').exists())
        self.assertFalse((self.root / 'job/source.npz').exists())

    def test_derived_adapter_tampering_is_detected(self):
        from autospine_workbench.automation.motion_generation_layout import verify
        from autospine_workbench.automation.motion_generation_provenance import identity
        layout = self.root / 'text-encoders'
        layout.mkdir()
        model = layout / 'adapter.bin'
        model.write_bytes(b'original fixture')
        (self.root / 'text-encoder-files.json').write_bytes(canonical_bytes({'adapter.bin': identity(model)}))
        verify(self.root)
        model.write_bytes(b'changed fixture')
        with self.assertRaisesRegex(ValueError, 'motion_generation_environment_changed'):
            verify(self.root)


if __name__ == '__main__':
    unittest.main()
