"""A lost response must not misreport a committed policy operation as invalid."""
from contextlib import ExitStack
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from autospine_workbench.automation.simple_binding_routes import dispatch


class BindingResponseDisconnectTest(unittest.TestCase):
    def setup_route(self, stack):
        handler = SimpleNamespace(server=object(), headers={}, _send_visual_json=MagicMock())
        manager = SimpleNamespace(application=SimpleNamespace(projects=object()))
        stack.enter_context(patch("autospine_workbench.automation.animated_routes.manager_for", return_value=manager))
        error = stack.enter_context(patch("autospine_workbench.automation.web_routes._error"))
        overview = stack.enter_context(patch("autospine_workbench.automation.simple_binding_routes.overview", return_value={"rows": []}))
        return handler, error, overview

    def test_committed_post_survives_disconnect_and_remains_readable(self):
        with ExitStack() as stack:
            handler, error, overview = self.setup_route(stack)
            stack.enter_context(patch("autospine_workbench.automation.web_routes._require_mutation"))
            body = dict(action="apply_all", expected_resolved_sha256="a"*64, expected_input_sha256="b"*64)
            stack.enter_context(patch("autospine_workbench.automation.simple_binding_routes.read_json_object_request", return_value=body))
            source = SimpleNamespace(source_addresses=dict(resolved_project_sha256="a"*64, input_identity_sha256="b"*64))
            loader = stack.enter_context(patch("autospine_workbench.automation.simple_binding_routes.load_inputs"))
            loader.return_value.__enter__.return_value = source
            operation = {"changed": True, "decision_sha256": "c"*64}
            applied = stack.enter_context(patch("autospine_workbench.automation.simple_binding_routes.apply_all", return_value=operation))
            handler._send_visual_json.side_effect = ConnectionAbortedError("client disconnected")
            self.assertTrue(dispatch([], handler, "POST", "fixture"))
            applied.assert_called_once()
            error.assert_not_called()
            self.assertEqual(handler._send_visual_json.call_count, 1)
            self.assertEqual(handler._send_visual_json.call_args.args[1]["operation"], operation)
            # A subsequent GET is read-only and can expose the committed state.
            overview.return_value = {"active_decision_sha256": "c"*64}
            handler._send_visual_json.side_effect = None
            self.assertTrue(dispatch([], handler, "GET", "fixture"))
            applied.assert_called_once()
            self.assertEqual(handler._send_visual_json.call_args.args, (200, overview.return_value))

    def test_analysis_failure_still_returns_domain_error(self):
        with ExitStack() as stack:
            handler, error, overview = self.setup_route(stack)
            overview.side_effect = OSError("unreadable evidence")
            self.assertTrue(dispatch([], handler, "GET", "fixture"))
            error.assert_called_once_with(handler, 400, "binding_policy_request_failed")
            handler._send_visual_json.assert_not_called()


if __name__ == "__main__":
    unittest.main()
