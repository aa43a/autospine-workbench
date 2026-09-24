from threading import RLock
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from autospine_workbench.automation.motion_intake_routes import dispatch_motions


class ViewErrorRouteTests(unittest.TestCase):
    def invoke(self, failure):
        handler=Mock()
        handler.server.automation_manager=SimpleNamespace(_lock=RLock(),_closed=False,_motions=Mock())
        with patch('autospine_workbench.automation.motion_view_template.download',side_effect=failure), \
             patch('autospine_workbench.automation.web_routes._error') as error:
            self.assertTrue(dispatch_motions(['api','motions','parent','view-pose-template','1'],handler,'GET'))
            return error.call_args.args

    def test_known_source_constraint_reaches_ui(self):
        args=self.invoke(ValueError('pose_variant_existing_attachment_timeline'))
        self.assertEqual(args[1:],(400,'pose_variant_existing_attachment_timeline'))

    def test_arbitrary_exception_text_is_not_public(self):
        for failure in (ValueError('view_private_path'),OSError('/private/path'),KeyError('view_pose_request_invalid')):
            with self.subTest(failure=str(failure)):
                self.assertEqual(self.invoke(failure)[1:],(400,'motion_request_failed'))
