"""Denied writes fail promptly; name collisions cannot overwrite prior bytes."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from autospine_workbench.staging_file import create_staging_file
from autospine_workbench.automation.storage_io import publish_document
from autospine_workbench.automation.pipeline_run import PipelineRunError
from autospine_workbench.benchmark.mesh_storage import export_mesh


class StagingFileTests(unittest.TestCase):
    def test_denied_write_is_not_retried(self):
        with patch('autospine_workbench.staging_file.os.open', side_effect=PermissionError) as opened:
            with self.assertRaises(PermissionError):
                create_staging_file(Path('unused'))
        self.assertEqual(opened.call_count, 1)

    def test_collision_preserves_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            old = Path(directory) / 'pending-old'
            old.write_bytes(b'keep')
            with patch('autospine_workbench.staging_file.secrets.token_hex', side_effect=['old', 'new']):
                fd, path = create_staging_file(directory)
            os.close(fd)
            self.assertEqual(old.read_bytes(), b'keep')
            self.assertEqual(path.read_bytes(), b'')

    def test_collision_limit_is_bounded(self):
        with patch('autospine_workbench.staging_file.os.open', side_effect=FileExistsError) as opened:
            with self.assertRaises(FileExistsError):
                create_staging_file(Path('unused'))
        self.assertEqual(opened.call_count, 32)

    def test_publish_denied_leaves_no_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch('autospine_workbench.automation.storage_io.create_staging_file', side_effect=PermissionError):
                with self.assertRaises(PipelineRunError) as error:
                    publish_document(root/'journal.json', {}, staging=root/'staging')
            self.assertEqual(error.exception.reason_code, 'pipeline_storage_invalid')
            doc = dict(schema='autospine.weighted-mesh-candidates/v1', authority='none', production_authorized=False)
            with patch('autospine_workbench.benchmark.mesh_storage.create_staging_file', side_effect=PermissionError):
                with self.assertRaises(PermissionError):
                    export_mesh(root/'mesh.json', doc)
            self.assertFalse((root/'journal.json').exists())
            self.assertFalse((root/'mesh.json').exists())
