"""HTTP security, routing, and stable conflicts for P10.2b framing."""

from __future__ import annotations

import http.client
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for candidate in (ROOT, SRC):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from autospine_workbench.capture_framing_application import (  # noqa: E402
    CaptureFramingApplicationHeadChanged,
    CaptureFramingApplicationInvalid,
)
from autospine_workbench.capture_framing_history import (  # noqa: E402
    CaptureFramingRevisionConflict,
)
from autospine_workbench.capture_framing_profile import (  # noqa: E402
    INTENT,
    SUBMISSION_FORMAT,
)
from autospine_workbench.server import create_server  # noqa: E402
from tests.test_project_store import StoreFixture  # noqa: E402


PACKAGE = "a" * 64
CANDIDATE = "b" * 64
PATH = (
    f"/api/idle-behavior/structural-probes/{PACKAGE}"
    "/capture-framing-decisions"
)
REQUEST = {
    "format": SUBMISSION_FORMAT,
    "format_version": 1,
    "intent": INTENT,
    "explicit_confirmation": True,
    "package_id": PACKAGE,
    "candidate_sha256": CANDIDATE,
    "p10_1_head": {
        "candidate_sha256": "c" * 64,
        "decision_sha256": "d" * 64,
        "revision": 1,
    },
    "base_revision": 0,
    "previous_decision_sha256": None,
    "action": "accept",
    "reason_code": "human-approved-automatic-capture-framing-v1",
    "world_viewport": None,
}
RECEIPT = {
    "format": "autospine-capture-framing-receipt",
    "format_version": 1,
    "status": "recorded",
    "project_id": "fixture-project",
    "package_id": PACKAGE,
    "candidate_sha256": CANDIDATE,
    "decision_sha256": "e" * 64,
    "revision": 1,
    "action": "accept",
    "decision_status": "ready_for_temporary_preview_v2",
    "reused": False,
    "history": {
        "current_revision": 1,
        "head_decision_sha256": "e" * 64,
    },
}


class CaptureFramingHttpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.fixture = StoreFixture(Path(self.temporary.name))
        self.server = create_server(
            "127.0.0.1", 0, self.fixture.workspace,
            state_root=self.fixture.state,
        )
        self.thread = threading.Thread(
            target=self.server.serve_forever, daemon=True,
        )
        self.thread.start()
        self.host, self.port = self.server.server_address[:2]
        self.authority = f"{self.host}:{self.port}"
        self.origin = f"http://{self.authority}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.temporary.cleanup()

    def _headers(self, **overrides):
        headers = {
            "Host": self.authority,
            "Origin": self.origin,
            "Content-Type": "application/json",
            "X-Autospine-Intent": INTENT,
            "Sec-Fetch-Site": "same-origin",
        }
        headers.update(overrides)
        return headers

    def _request(self, method, *, body=REQUEST, headers=None):
        connection = http.client.HTTPConnection(
            self.host, self.port, timeout=5,
        )
        raw = None if body is None else json.dumps(body).encode("utf-8")
        connection.request(method, PATH, body=raw, headers=headers or {})
        response = connection.getresponse()
        data = response.read()
        result = (
            response.status,
            {key.lower(): value for key, value in response.getheaders()},
            json.loads(data.decode("utf-8")) if data else None,
        )
        connection.close()
        return result

    def test_post_is_same_origin_intent_bound_and_path_free(self):
        target = (
            "autospine_workbench.capture_framing_routes."
            "CaptureFramingApplication.submit"
        )
        with patch(target, return_value=RECEIPT) as submit:
            status, headers, result = self._request(
                "POST", headers=self._headers(),
            )
        self.assertEqual(200, status)
        self.assertEqual(RECEIPT, result)
        self.assertEqual(self.origin, headers["access-control-allow-origin"])
        self.assertEqual("same-origin", headers["cross-origin-resource-policy"])
        submit.assert_called_once_with(PACKAGE, REQUEST)
        self.assertNotIn(str(self.fixture.state), json.dumps(result))

    def test_missing_origin_wrong_intent_and_cross_site_never_reach_app(self):
        cases = [
            {"Host": self.authority, "Content-Type": "application/json",
             "X-Autospine-Intent": INTENT},
            self._headers(**{"X-Autospine-Intent": "wrong"}),
            self._headers(**{"Sec-Fetch-Site": "cross-site"}),
        ]
        target = (
            "autospine_workbench.capture_framing_routes."
            "CaptureFramingApplication.submit"
        )
        with patch(target, return_value=RECEIPT) as submit:
            for headers in cases:
                with self.subTest(headers=headers):
                    status, _response_headers, result = self._request(
                        "POST", headers=headers,
                    )
                    self.assertEqual(403, status)
                    self.assertTrue(result["error"].startswith("forbidden_"))
        submit.assert_not_called()

    def test_invalid_confirmation_head_change_and_revision_are_stable(self):
        target = (
            "autospine_workbench.capture_framing_routes."
            "CaptureFramingApplication.submit"
        )
        errors = [
            (CaptureFramingApplicationInvalid("bad"), 400,
             "invalid_capture_framing_submission"),
            (CaptureFramingApplicationHeadChanged("changed"), 409,
             "capture_framing_source_changed"),
            (CaptureFramingRevisionConflict(
                "stale", requested_revision=1, current_revision=2,
                requested_head=None, current_head="f" * 64,
            ), 409, "capture_framing_revision_conflict"),
        ]
        for error, expected_status, code in errors:
            with self.subTest(code=code), patch(target, side_effect=error):
                status, _headers, result = self._request(
                    "POST", headers=self._headers(),
                )
            self.assertEqual(expected_status, status)
            self.assertEqual(code, result["error"])
            self.assertNotIn("path", json.dumps(result).lower())

    def test_options_and_other_methods_publish_exact_allow_contract(self):
        status, headers, result = self._request(
            "OPTIONS", body=None,
            headers={"Host": self.authority, "Origin": self.origin},
        )
        self.assertEqual(204, status)
        self.assertIsNone(result)
        self.assertEqual("POST, OPTIONS", headers["allow"])
        self.assertEqual(
            "Content-Type, X-Autospine-Intent",
            headers["access-control-allow-headers"],
        )
        for method in ("GET", "PUT", "PATCH", "DELETE"):
            with self.subTest(method=method):
                status, response_headers, result = self._request(
                    method, body=None,
                    headers={"Host": self.authority, "Origin": self.origin},
                )
                self.assertEqual(405, status)
                self.assertEqual("POST, OPTIONS", response_headers["allow"])
                self.assertEqual("method_not_allowed", result["error"])


if __name__ == "__main__":
    unittest.main()
