"""HTTP routing and explicit-intent tests for asynchronous P10 capture."""

from __future__ import annotations

import http.client
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for candidate in (ROOT, SRC):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from autospine_workbench.p10_runtime_capture_http_security import (  # noqa: E402
    INTENT,
)
from autospine_workbench.server import create_server  # noqa: E402
from tests.test_project_store import StoreFixture  # noqa: E402


SHA = "a" * 64


class P10RuntimeCaptureHttpTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.fixture = StoreFixture(Path(self.temporary.name))
        self.manager = Mock()
        self.manager.prepare.return_value = {"format": "preflight"}
        self.manager.submit.return_value = {"job_id": SHA, "status": "queued"}
        self.manager.get.return_value = {"job_id": SHA, "status": "capturing"}
        self.manager.close = Mock()
        self.manager_patch = patch(
            "autospine_workbench.server.P10CaptureJobManager",
            return_value=self.manager,
        )
        self.manager_patch.start()
        self.server = create_server(
            "127.0.0.1", 0, self.fixture.workspace,
            state_root=self.fixture.state,
        )
        self.thread = threading.Thread(
            target=self.server.serve_forever, daemon=True,
        )
        self.thread.start()
        self.host, self.port = self.server.server_address[:2]

    def tearDown(self):
        self.close_server()
        self.manager_patch.stop()
        self.temporary.cleanup()

    def close_server(self):
        if self.server is None:
            return
        self.server.shutdown()
        self.thread.join(timeout=5)
        self.server.server_close()
        self.server = None

    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection(self.host, self.port, timeout=5)
        payload = None if body is None else json.dumps(body).encode("utf-8")
        actual_headers = dict(headers or {})
        if payload is not None:
            actual_headers.setdefault("Content-Type", "application/json")
        connection.request(method, path, body=payload, headers=actual_headers)
        response = connection.getresponse()
        raw = response.read()
        result = (
            response.status,
            {key.lower(): value for key, value in response.getheaders()},
            json.loads(raw.decode("utf-8")) if raw else None,
        )
        connection.close()
        return result

    def mutation_headers(self):
        return {
            "Origin": f"http://{self.host}:{self.port}",
            "Sec-Fetch-Site": "same-origin",
            "X-Autospine-Intent": INTENT,
        }

    def test_preflight_submit_poll_and_close_are_wired(self):
        status, _, value = self.request(
            "GET", f"/api/p10/runtime-capture/packages/{SHA}",
        )
        self.assertEqual(200, status)
        self.assertEqual("preflight", value["format"])
        self.manager.prepare.assert_called_once_with(SHA)

        body = {"package_id": SHA, "explicit_run_confirmation": True}
        status, _, value = self.request(
            "POST", "/api/p10/runtime-capture/jobs", body,
            self.mutation_headers(),
        )
        self.assertEqual(202, status)
        self.assertEqual(SHA, value["job_id"])
        self.manager.submit.assert_called_once_with(body)

        status, _, value = self.request(
            "GET", f"/api/p10/runtime-capture/jobs/{SHA}",
        )
        self.assertEqual(200, status)
        self.assertEqual("capturing", value["status"])
        self.manager.get.assert_called_once_with(SHA)

        self.close_server()
        self.manager.close.assert_called()

    def test_mutation_requires_origin_and_exact_intent(self):
        for headers in ({}, {
            "Origin": f"http://{self.host}:{self.port}",
            "X-Autospine-Intent": "wrong",
        }):
            with self.subTest(headers=headers):
                status, _, value = self.request(
                    "POST", "/api/p10/runtime-capture/jobs",
                    {"package_id": SHA}, headers,
                )
                self.assertEqual(403, status)
                self.assertTrue(value["error"].startswith("forbidden_"))
        self.manager.submit.assert_not_called()

    def test_options_and_wrong_methods_publish_exact_allow(self):
        status, headers, _ = self.request(
            "OPTIONS", "/api/p10/runtime-capture/jobs",
        )
        self.assertEqual(204, status)
        self.assertEqual("POST, OPTIONS", headers["allow"])
        status, headers, value = self.request(
            "PUT", f"/api/p10/runtime-capture/jobs/{SHA}", {},
        )
        self.assertEqual(405, status)
        self.assertEqual("GET, HEAD, OPTIONS", headers["allow"])
        self.assertEqual("method_not_allowed", value["error"])

        for method, path, allow in (
            ("GET", "/api/p10/runtime-capture/jobs", "POST, OPTIONS"),
            ("PATCH", f"/api/p10/runtime-capture/jobs/{SHA}", "GET, HEAD, OPTIONS"),
            ("DELETE", "/api/p10/runtime-capture/jobs", "POST, OPTIONS"),
        ):
            with self.subTest(method=method, path=path):
                status, headers, value = self.request(method, path, {})
                self.assertEqual(405, status)
                self.assertEqual(allow, headers["allow"])
                self.assertEqual("method_not_allowed", value["error"])


if __name__ == "__main__":
    unittest.main()
