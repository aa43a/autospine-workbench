"""PSD upload exercises the real decoder, project discovery, and durable jobs."""
from hashlib import sha256
import importlib.util
from io import BytesIO
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from autospine_workbench.automation.asset_library import AssetLibrary
from autospine_workbench.automation.pipeline_run import PipelineRunError
from autospine_workbench.automation.psd_import_jobs import PsdImportJobs
from autospine_workbench.automation.psd_intake_worker import PsdIntakeError
from autospine_workbench.automation.storage_io import publish_document
from autospine_workbench.project_store import ProjectStore


class PsdImportJobsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.projects = ProjectStore(self.root, self.root / 'state', measure_composite_quality=False)
        self.manager = PsdImportJobs(self.projects)
        self.addCleanup(self.manager.close)
        self.header = struct.pack('>4sH6sHIIHH', b'8BPS', 1, bytes(6), 4, 24, 24, 8, 3)

    def upload(self, payload=None, name='角色.psd'):
        payload = self.header if payload is None else payload
        return self.manager.upload(BytesIO(payload), len(payload), name)

    def test_filename_and_bad_header_never_publish_project(self):
        for name in ('../bad.psd', 'bad.png', 'bad\n.psd'):
            with self.assertRaises(PipelineRunError):
                self.upload(name=name)
        with self.assertRaises(PsdIntakeError):
            self.upload(b'not a photoshop document at all')
        self.assertEqual(self.projects.list_projects(), [])

    def test_incomplete_upload_never_invokes_decoder(self):
        with patch('autospine_workbench.automation.psd_import_jobs.subprocess.run') as run:
            with self.assertRaises(PipelineRunError) as raised:
                self.manager.upload(BytesIO(self.header), len(self.header) + 10, 'short.psd')
        self.assertEqual(raised.exception.reason_code, 'psd_upload_incomplete')
        run.assert_not_called()
        self.assertEqual(self.projects.list_projects(), [])

    def test_decoder_failure_is_structured_and_durable(self):
        result = subprocess.CompletedProcess([], 1, b'{"reason_code":"psd_layer_kind_unsupported"}', b'')
        with patch('autospine_workbench.automation.psd_import_jobs.subprocess.run', return_value=result):
            queued = self.upload()
            self.manager.close()
        failed = self.manager.get(queued['job_id'])
        self.assertEqual(failed['status'], 'failed')
        self.assertEqual(failed['reason_code'], 'psd_layer_kind_unsupported')
        restarted = PsdImportJobs(self.projects)
        self.addCleanup(restarted.close)
        self.assertEqual(restarted.get(queued['job_id']), failed)
        self.assertEqual(self.projects.list_projects(), [])

    def test_timeout_has_specific_reason(self):
        with patch('autospine_workbench.automation.psd_import_jobs.subprocess.run',
                   side_effect=subprocess.TimeoutExpired('decoder', 180)):
            queued = self.upload()
            self.manager.close()
        self.assertEqual(self.manager.get(queued['job_id'])['reason_code'], 'psd_decode_timeout')

    def test_restart_incomplete_job_reports_interrupted(self):
        job = 'import-' + 'a' * 32
        folder = self.manager.folder(job, create=True)
        publish_document(folder / 'request.json', {'job_id': job}, staging=folder / 'staging')
        self.assertEqual(self.manager.get(job)['reason_code'], 'psd_import_interrupted')
        with self.assertRaises(PipelineRunError):
            self.manager.get('../escape')

    def test_existing_destination_with_wrong_source_fails_without_overwrite(self):
        destination = self.projects.audit_root / ('imported-' + sha256(self.header).hexdigest())
        destination.mkdir(parents=True)
        path = destination / 'audit.json'
        original = json.dumps({'sha256': 'b' * 64}).encode()
        path.write_bytes(original)
        with patch('autospine_workbench.automation.psd_import_jobs.subprocess.run') as run:
            queued = self.upload()
            self.manager.close()
        self.assertEqual(self.manager.get(queued['job_id'])['reason_code'], 'psd_source_conflict')
        self.assertEqual(path.read_bytes(), original)
        run.assert_not_called()

    @unittest.skipUnless(importlib.util.find_spec('psd_tools') and importlib.util.find_spec('PIL'),
                         'optional PSD decoder unavailable')
    def test_real_async_upload_discovery_and_duplicate_preserve_evidence(self):
        from PIL import Image
        from psd_tools import PSDImage
        from psd_tools.api.layers import PixelLayer
        psd = PSDImage.new('RGBA', (24, 24))
        PixelLayer.frompil(Image.new('RGBA', (5, 8), (255, 0, 0, 255)),
                           psd, name='handwear-r', left=7, top=8)
        source = self.root / 'test.psd'
        psd.save(source)
        payload = source.read_bytes()
        queued = self.upload(payload)
        self.manager.close()
        done = self.manager.get(queued['job_id'])
        self.assertEqual(done['status'], 'succeeded', done)
        expected = 'imported-' + sha256(payload).hexdigest()
        self.assertEqual(done['project_id'], expected)
        self.assertEqual([p['id'] for p in self.projects.list_projects()], [expected])
        self.assertTrue(self.projects.resolve_asset(expected, 'composite').is_file())
        audit = self.projects.audit_root / expected
        before = {p.relative_to(audit): p.read_bytes() for p in audit.rglob('*') if p.is_file()}
        library = AssetLibrary(self.projects)
        library.change(expected, {'action': 'archive', 'expected_revision': 1})
        metadata = library.metadata(expected)
        restarted = PsdImportJobs(self.projects)
        self.addCleanup(restarted.close)
        self.assertEqual(restarted.get(queued['job_id']), done)
        with patch('autospine_workbench.automation.psd_import_jobs.subprocess.run') as run:
            again = restarted.upload(BytesIO(payload), len(payload), 'renamed.psd')
            restarted.close()
        run.assert_not_called()
        self.assertEqual(restarted.get(again['job_id'])['status'], 'succeeded')
        self.assertEqual(library.metadata(expected), metadata)
        self.assertEqual({p.relative_to(audit): p.read_bytes() for p in audit.rglob('*') if p.is_file()}, before)


if __name__ == '__main__':
    unittest.main()
