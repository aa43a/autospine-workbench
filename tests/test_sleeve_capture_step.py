import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from autospine_workbench.automation.sleeve_capture_step import run,checked_summary
from autospine_workbench.automation.sleeve_capture_environment import discover


class SleeveCaptureStepTests(unittest.TestCase):
    def test_missing_dependencies_do_not_launch_or_install(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(discover(Path(folder)),[])

    def test_changed_environment_rejects_even_cached_stage(self):
        report=dict(records=[dict(download='candidate.zip')])
        with patch('autospine_workbench.automation.sleeve_capture_step.identity',return_value={'changed':True}):
            with self.assertRaisesRegex(ValueError,'environment_changed'):
                run(Path('.'),Path('.'),'fixture',Path('.'),Path('.'),{},report,lambda:None)

    def test_capture_failure_blocks_download_and_success_keeps_review(self):
        for failed in (0,1):
            with tempfile.TemporaryDirectory() as folder:
                root=Path(folder);out=root/'framebuffer/fixture/layer-part';out.mkdir(parents=True)
                (out/'receipt.json').write_text('{}')
                report=dict(run_id='run',steps=[],records=[dict(layer_id='layer',component_id='part',
                    status='candidate_exported',download='candidate.zip')])
                with patch('autospine_workbench.automation.sleeve_capture_step.identity',return_value={}), \
                     patch('autospine_workbench.automation.sleeve_capture_step.checkpoint',return_value=dict(id='framebuffer',cached=True)), \
                     patch('autospine_workbench.automation.sleeve_capture_step.checked_summary',return_value=dict(failed_samples=failed)):
                    result=run(root,root,'fixture',root,root,{},report,lambda:None)
                self.assertEqual(result['records'][0]['status'],'blocked' if failed else 'candidate_exported')
                self.assertEqual(result['records'][0]['download'],None if failed else 'candidate.zip')

    def test_receipt_byte_tampering_rejected_before_consumption(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);path=root/('0'*64+'.json');path.write_text('{"project_id":"fixture"}')
            with self.assertRaisesRegex(ValueError,'receipt'):checked_summary(path,root,'fixture',{}, {},root)
