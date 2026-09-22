"""Motion selection is read-only and uses the source-validating job reader."""
import unittest
from unittest.mock import Mock, patch
from autospine_workbench.automation.character_routes import dispatch_character


class MotionTargetRouteTests(unittest.TestCase):
    def test_get_uses_target_reader_and_post_is_rejected(self):
        handler, manager = Mock(), Mock()
        expected = dict(project_id='sample', authority='none', job=None)
        manager.motion_target.return_value = expected
        with patch('autospine_workbench.automation.character_routes.manager_for', return_value=manager):
            self.assertTrue(dispatch_character(['motion-target'], handler, 'GET', 'sample'))
            manager.motion_target.assert_called_once_with('sample')
            manager.overview.assert_not_called()
            handler._send_visual_json.assert_called_once_with(200, expected)
            dispatch_character(['motion-target'], handler, 'POST', 'sample')
            self.assertEqual(handler._send_bytes.call_args.args[0], 405)
            manager.submit.assert_not_called()


if __name__ == '__main__':
    unittest.main()
