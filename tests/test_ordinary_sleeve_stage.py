import tempfile
from pathlib import Path
import unittest
from autospine_workbench.automation.ordinary_sleeve_stage import read_stage
from autospine_workbench.automation.sleeve_review_files import read
from autospine_workbench.automation.sleeve_workflow import checkpoint
from autospine_workbench.automation.pipeline_run import PipelineRunError
from autospine_workbench.benchmark.mesh_storage import publish_mesh_report,export_mesh


class OrdinarySleeveStageTests(unittest.TestCase):
    def test_stage_requires_exact_stored_project_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);folder=root/'input'/'fresh';folder.mkdir(parents=True)
            doc=dict(schema='autospine.ordinary-deform-target/v1',project_id='fresh',authority='none',production_authorized=False)
            sha=publish_mesh_report(root/'state','project-component-partitions',doc)
            export_mesh(folder/(sha+'.json'),doc)
            self.assertEqual(read_stage(root/'input','fresh',root/'state'),doc)
            (folder/(sha+'.json')).write_text('{}')
            with self.assertRaisesRegex(ValueError,'stage_source'):read_stage(root/'input','fresh',root/'state')

    def test_review_is_receipt_checked_and_project_scoped(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);output=root/'ordinary-deform';folder=output/'fresh'
            def execute():folder.mkdir(parents=True);(folder/'index.html').write_bytes(b'comparison')
            checkpoint(root,'ordinary-deform','a'*64,output,execute)
            report=dict(steps=[dict(id='ordinary-deform',status='succeeded')])
            parts=['ordinary-deform','fresh','index.html']
            self.assertEqual(read(root,'fresh',report,parts)[0],b'comparison')
            with self.assertRaises(PipelineRunError):read(root,'other',report,parts)
            with self.assertRaises(PipelineRunError):read(root,'fresh',dict(steps=[]),parts)
            (folder/'index.html').write_bytes(b'changed')
            with self.assertRaises(PipelineRunError):read(root,'fresh',report,parts)
