"""HTTP routing and security tests for asynchronous P10.4b v2 analysis."""

from __future__ import annotations

import http.client
import json
from email.message import Message
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

from autospine_workbench.p10_safety_analysis_manager_v2 import (  # noqa: E402
    P10SafetyAnalysisManagerV2Error,
)
from autospine_workbench.p10_safety_analysis_v2_http_security import (  # noqa: E402
    INTENT, P10SafetyAnalysisV2HttpSecurityError,
    require_p10_safety_analysis_v2_headers,
    require_p10_safety_analysis_v2_read_headers,
)
from autospine_workbench.server import create_server  # noqa: E402
from tests.test_project_store import StoreFixture  # noqa: E402


JOB_ID = "a" * 64
RUN_ID = "b" * 64


def _run(status="running"):
    return {
        "run_id": RUN_ID, "status": status,
        "stage": "continuous_segments",
        "progress": {"current": 3, "total": 9},
        "failure_code": None,
    }


class P10SafetyAnalysisV2HttpTests(unittest.TestCase):
    def test_security_contract_accepts_loopback_and_rejects_duplicates(self):
        for host in ("127.0.0.1:8765", "localhost:8765", "[::1]:8765"):
            headers = Message()
            headers["Host"] = host
            headers["Origin"] = f"http://{host}"
            headers["X-Autospine-Intent"] = INTENT
            headers["Sec-Fetch-Site"] = "none"
            require_p10_safety_analysis_v2_headers(headers)
        self.assertNotEqual("p10-body-sway-visual-review-v2", INTENT)
        self.assertNotEqual("p10-official-runtime-capture-v2", INTENT)
        headers["Origin"] = f"http://{host}"
        with self.assertRaises(P10SafetyAnalysisV2HttpSecurityError):
            require_p10_safety_analysis_v2_headers(headers)

        read_headers = Message()
        require_p10_safety_analysis_v2_read_headers(read_headers)
        read_headers["Sec-Fetch-Site"] = "same-origin"
        require_p10_safety_analysis_v2_read_headers(read_headers)
        read_headers.replace_header("Sec-Fetch-Site", "cross-site")
        with self.assertRaises(P10SafetyAnalysisV2HttpSecurityError):
            require_p10_safety_analysis_v2_read_headers(read_headers)

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.fixture = StoreFixture(Path(self.temporary.name))
        self.capture = Mock()
        self.capture.close = Mock()
        self.safety = Mock()
        self.safety.close = Mock()
        self.safety.entry.return_value = {
            "ok": True, "status": "ready", "job_id": JOB_ID,
        }
        self.safety.submit.return_value = {
            "ok": True, "status": "queued", "job_id": JOB_ID,
            "run": _run("queued"),
        }
        self.safety.get.return_value = {
            "ok": True, "status": "running", "job_id": JOB_ID,
            "run": _run(),
        }
        self.safety.result.return_value = {
            "ok": True, "status": "completed", "job_id": JOB_ID,
            "run": _run("completed"), "project_id": "sample",
            "clip_id": "wave-left-v1", "amplitude": {},
            "continuous": {}, "claims": {},
            "release_gate": {"status": "blocked"}, "documents": {},
        }
        self.capture_patch = patch(
            "autospine_workbench.server.P10CaptureJobManager",
            return_value=self.capture,
        )
        self.safety_patch = patch(
            "autospine_workbench.server.P10SafetyAnalysisManagerV2",
            return_value=self.safety,
        )
        self.capture_patch.start()
        self.safety_factory = self.safety_patch.start()
        self.server = create_server(
            "127.0.0.1", 0, self.fixture.workspace,
            web_root=ROOT / "web", state_root=self.fixture.state,
        )
        self.thread = threading.Thread(
            target=self.server.serve_forever, daemon=True,
        )
        self.thread.start()
        self.host, self.port = self.server.server_address[:2]
        self.base = (
            f"/api/p10/runtime-capture/jobs/{JOB_ID}"
            "/visual-review-v2/safety-analysis-v2"
        )

    def tearDown(self):
        self.close_server()
        self.safety_patch.stop()
        self.capture_patch.stop()
        self.temporary.cleanup()

    def close_server(self):
        if self.server is None:
            return
        self.server.shutdown()
        self.thread.join(timeout=5)
        self.server.server_close()
        self.server = None

    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection(
            self.host, self.port, timeout=5,
        )
        encoded = json.dumps(body).encode("utf-8") \
            if isinstance(body, dict) else body
        actual = dict(headers or {})
        if encoded is not None:
            actual.setdefault("Content-Type", "application/json")
        connection.request(method, path, body=encoded, headers=actual)
        response = connection.getresponse()
        raw = response.read()
        response_headers = {
            key.lower(): value for key, value in response.getheaders()
        }
        result = (
            response.status,
            response_headers,
            json.loads(raw.decode("utf-8"))
            if raw and "application/json" in response_headers.get(
                "content-type", ""
            ) else raw,
        )
        connection.close()
        return result

    def mutation_headers(self):
        return {
            "Origin": f"http://{self.host}:{self.port}",
            "Sec-Fetch-Site": "same-origin",
            "X-Autospine-Intent": INTENT,
        }

    def test_entry_start_poll_result_and_lifecycle_are_wired(self):
        status, _, entry = self.request("GET", self.base)
        self.assertEqual(200, status)
        self.assertEqual("ready", entry["status"])
        self.safety.entry.assert_called_once_with(JOB_ID)

        status, _, queued = self.request(
            "POST", f"{self.base}/runs", {}, self.mutation_headers(),
        )
        self.assertEqual(202, status)
        self.assertEqual(RUN_ID, queued["run"]["run_id"])
        self.safety.submit.assert_called_once_with(JOB_ID)

        status, _, running = self.request(
            "GET", f"{self.base}/runs/{RUN_ID}",
        )
        self.assertEqual(200, status)
        self.assertEqual("running", running["status"])
        self.safety.get.assert_called_once_with(JOB_ID, RUN_ID)

        status, _, result = self.request(
            "GET", f"{self.base}/runs/{RUN_ID}/result",
        )
        self.assertEqual(200, status)
        self.assertEqual("blocked", result["release_gate"]["status"])
        self.safety.result.assert_called_once_with(JOB_ID, RUN_ID)

        self.safety_factory.assert_called_once_with(
            self.capture, self.server.project_store,
        )
        self.close_server()
        self.safety.close.assert_called_once_with()
        self.capture.close.assert_called_once_with()

    def test_start_requires_same_origin_intent_and_empty_object(self):
        attempts = (
            ({}, "forbidden_origin"),
            ({"Origin": f"http://{self.host}:{self.port}",
              "X-Autospine-Intent": "wrong"}, "forbidden_intent"),
            ({**self.mutation_headers(),
              "Sec-Fetch-Site": "cross-site"}, "forbidden_fetch_site"),
        )
        for headers, error in attempts:
            with self.subTest(error=error):
                status, _, value = self.request(
                    "POST", f"{self.base}/runs", {}, headers,
                )
                self.assertEqual(403, status)
                self.assertEqual(error, value["error"])
        status, _, value = self.request(
            "POST", f"{self.base}/runs", {"unexpected": True},
            self.mutation_headers(),
        )
        self.assertEqual(400, status)
        self.assertEqual("invalid_safety_analysis_v2_request", value["error"])
        self.safety.submit.assert_not_called()

    def test_specific_route_precedes_visual_family_and_publishes_methods(self):
        cases = (
            (self.base, "GET, HEAD, OPTIONS"),
            (f"{self.base}/runs", "POST, OPTIONS"),
            (f"{self.base}/runs/{RUN_ID}", "GET, HEAD, OPTIONS"),
            (f"{self.base}/runs/{RUN_ID}/result", "GET, OPTIONS"),
        )
        for path, allow in cases:
            with self.subTest(path=path):
                status, headers, value = self.request("OPTIONS", path)
                self.assertEqual(204, status)
                self.assertEqual(allow, headers["allow"])
                self.assertEqual(b"", value)
        status, headers, value = self.request("GET", f"{self.base}/runs")
        self.assertEqual(405, status)
        self.assertEqual("POST, OPTIONS", headers["allow"])
        self.assertEqual("method_not_allowed", value["error"])

        self.safety.result.reset_mock()
        status, headers, value = self.request(
            "HEAD", f"{self.base}/runs/{RUN_ID}/result",
            headers={"Sec-Fetch-Site": "same-origin"},
        )
        self.assertEqual(405, status)
        self.assertEqual("GET, OPTIONS", headers["allow"])
        self.assertEqual(b"", value)
        self.safety.result.assert_not_called()
        status, headers, value = self.request("PUT", self.base, {})
        self.assertEqual(405, status)
        self.assertEqual("GET, HEAD, OPTIONS", headers["allow"])
        self.assertEqual("method_not_allowed", value["error"])

        status, headers, _ = self.request(
            "GET", "/body-sway-safety-analysis-v2.html",
        )
        self.assertEqual(200, status)
        self.assertIn("default-src 'self'", headers["content-security-policy"])

    def test_manager_failures_are_redacted_and_cross_job_run_is_not_found(self):
        self.safety.entry.side_effect = P10SafetyAnalysisManagerV2Error(
            r"private E:\secret\admission.json",
        )
        status, _, value = self.request("GET", self.base)
        self.assertEqual(409, status)
        self.assertEqual("safety_analysis_v2_not_ready", value["error"])
        self.assertNotIn("secret", json.dumps(value).lower())

        self.safety.get.side_effect = P10SafetyAnalysisManagerV2Error(
            "run belongs to another job"
        )
        status, _, value = self.request(
            "GET", f"{self.base}/runs/{RUN_ID}",
        )
        self.assertEqual(404, status)
        self.assertEqual("safety_analysis_v2_not_found", value["error"])

    def test_cross_site_reads_fail_before_any_manager_work(self):
        cases = (
            ("GET", self.base),
            ("HEAD", self.base),
            ("GET", f"{self.base}/runs/{RUN_ID}"),
            ("HEAD", f"{self.base}/runs/{RUN_ID}"),
            ("GET", f"{self.base}/runs/{RUN_ID}/result"),
            ("HEAD", f"{self.base}/runs/{RUN_ID}/result"),
        )
        for method, path in cases:
            with self.subTest(method=method, path=path):
                status, _, value = self.request(
                    method, path,
                    headers={"Sec-Fetch-Site": "cross-site"},
                )
                self.assertEqual(403, status)
                if method == "GET":
                    self.assertEqual("forbidden_fetch_site", value["error"])
                else:
                    self.assertEqual(b"", value)
        self.safety.entry.assert_not_called()
        self.safety.get.assert_not_called()
        self.safety.result.assert_not_called()


if __name__ == "__main__":
    unittest.main()
