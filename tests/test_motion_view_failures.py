from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from autospine_workbench.automation.motion_intake_process import failure_reason
from autospine_workbench.automation.motion_view_failures import VIEW_FAILURES


class ViewFailureTests(unittest.TestCase):
    def test_known_codes_survive_worker_log_boundary(self):
        with TemporaryDirectory() as folder:
            path=Path(folder)/'worker.log'
            for code in VIEW_FAILURES:
                with self.subTest(code=code):
                    path.write_text('diagnostic\n'+json.dumps({'reason_code':code}),encoding='utf-8')
                    self.assertEqual(failure_reason(path),code)

    def test_unknown_view_messages_are_not_exposed(self):
        with TemporaryDirectory() as folder:
            path=Path(folder)/'worker.log'
            for code in ('view_private_path', 'view_candidate_texture_changed /local/private', None):
                path.write_text(json.dumps({'reason_code':code}),encoding='utf-8')
                self.assertEqual(failure_reason(path),'motion_decode_failed')
