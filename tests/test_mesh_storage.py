"""Mesh-specific byte budgets and immutable output verification."""
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from autospine_workbench.benchmark.mesh_storage import publish_mesh_report,read_mesh_report,export_mesh


class MeshStorageTests(unittest.TestCase):
    def test_large_report_replay_conflict_and_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            doc={'schema':'autospine.weighted-mesh-candidates/v1','authority':'none','production_authorized':False,'payload':'x'*140000}
            digest=publish_mesh_report(root,'fixture',doc)
            self.assertEqual(read_mesh_report(root,'fixture',digest),doc)
            self.assertEqual(publish_mesh_report(root,'fixture',doc),digest)
            out=root/'export.json';export_mesh(out,doc)
            with self.assertRaises(ValueError):export_mesh(out,{**doc,'payload':'different'})
            with patch('autospine_workbench.benchmark.mesh_storage.MAX_BYTES',128):
                with self.assertRaises(ValueError):publish_mesh_report(root,'fixture',doc)
            out.write_text('{}',encoding='utf-8')
            with self.assertRaises(ValueError):export_mesh(out,doc)
