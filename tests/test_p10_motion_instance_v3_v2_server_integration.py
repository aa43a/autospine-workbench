"""Server wiring and lifecycle regression for automatic P10.6b v2."""

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

from autospine_workbench.p10_motion_instance_v3_manager_v2 import (  # noqa: E402
    P10MotionInstanceV3ManagerV2Error,
)
from autospine_workbench.server import create_server  # noqa: E402
from tests.test_project_store import StoreFixture  # noqa: E402


JOB, SAFETY, DYNAMIC, RUN = (character * 64 for character in "abcd")


class P10MotionInstanceV3V2ServerIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.fixture = StoreFixture(Path(self.temporary.name))
        self.close_order = []
        self.capture = self._manager("capture")
        self.safety = self._manager("safety")
        self.dynamic = self._manager("dynamic")
        self.motion = self._manager("motion")
        self.motion.entry.return_value = _value("ready")
        self.motion.submit.return_value = _value("queued")
        self.motion.get.return_value = _value("running")
        self.motion.result.return_value = _value("completed")
        self.patches = [
            patch("autospine_workbench.server.P10CaptureJobManager",
                  return_value=self.capture),
            patch("autospine_workbench.server.P10SafetyAnalysisManagerV2",
                  return_value=self.safety),
            patch("autospine_workbench.server.P10DynamicSeamManagerV2",
                  return_value=self.dynamic),
            patch("autospine_workbench.server.P10MotionInstanceV3ManagerV2",
                  return_value=self.motion),
        ]
        for current in self.patches:
            current.start()
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
            f"/api/p10/runtime-capture/jobs/{JOB}/visual-review-v2/"
            f"safety-analysis-v2/runs/{SAFETY}/dynamic-seam-v2/"
            f"runs/{DYNAMIC}/motion-instance-v3-v2"
        )

    def tearDown(self):
        self._close_server()
        for current in reversed(self.patches):
            current.stop()
        self.temporary.cleanup()

    def _manager(self, name):
        manager = Mock()
        manager.close.side_effect = lambda: self.close_order.append(name)
        return manager

    def _close_server(self):
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
        value = json.loads(raw.decode("utf-8")) \
            if raw and "application/json" in response_headers.get(
                "content-type", "",
            ) else raw
        connection.close()
        return response.status, response_headers, value

    def mutation_headers(self):
        return {
            "Origin": f"http://{self.host}:{self.port}",
            "Sec-Fetch-Site": "same-origin",
            "X-Autospine-Intent":
                "p10-body-sway-motion-instance-v3-v2",
        }

    def test_static_page_and_exact_api_lifecycle_are_wired(self):
        status, headers, raw = self.request(
            "GET", "/motion-instance-v3-v2.html",
        )
        self.assertEqual(200, status)
        self.assertTrue(raw)
        self.assertIn("default-src 'self'",
                      headers["content-security-policy"])

        self.assertEqual(200, self.request("GET", self.base)[0])
        self.motion.entry.assert_called_once_with(JOB, SAFETY, DYNAMIC)
        status, _, queued = self.request(
            "POST", f"{self.base}/runs", {}, self.mutation_headers(),
        )
        self.assertEqual(202, status)
        self.assertEqual("queued", queued["status"])
        self.motion.submit.assert_called_once_with(JOB, SAFETY, DYNAMIC)
        self.assertEqual(
            200, self.request("GET", f"{self.base}/runs/{RUN}")[0],
        )
        self.motion.get.assert_called_once_with(JOB, SAFETY, DYNAMIC, RUN)
        self.assertEqual(200, self.request(
            "GET", f"{self.base}/runs/{RUN}/result",
        )[0])
        self.motion.result.assert_called_once_with(
            JOB, SAFETY, DYNAMIC, RUN,
        )

    def test_options_and_wrong_methods_use_the_nested_route_policy(self):
        cases = (
            (self.base, "GET, HEAD, OPTIONS"),
            (f"{self.base}/runs", "POST, OPTIONS"),
            (f"{self.base}/runs/{RUN}", "GET, HEAD, OPTIONS"),
            (f"{self.base}/runs/{RUN}/result", "GET, OPTIONS"),
        )
        for path, allow in cases:
            with self.subTest(path=path):
                status, headers, value = self.request("OPTIONS", path)
                self.assertEqual(204, status)
                self.assertEqual(allow, headers["allow"])
                self.assertEqual(b"", value)
        wrong = (
            ("GET", f"{self.base}/runs", "POST, OPTIONS"),
            ("HEAD", f"{self.base}/runs/{RUN}/result", "GET, OPTIONS"),
            ("PUT", self.base, "GET, HEAD, OPTIONS"),
            ("PATCH", self.base, "GET, HEAD, OPTIONS"),
        )
        for method, path, allow in wrong:
            with self.subTest(method=method, path=path):
                status, headers, _ = self.request(method, path)
                self.assertEqual(405, status)
                self.assertEqual(allow, headers["allow"])

    def test_server_close_closes_each_manager_once_in_reverse_order(self):
        self._close_server()
        self.assertEqual(
            ["motion", "dynamic", "safety", "capture"],
            self.close_order,
        )
        for manager in (
            self.motion, self.dynamic, self.safety, self.capture,
        ):
            manager.close.assert_called_once_with()


class P10MotionInstanceV3V2StartupLifecycleTests(unittest.TestCase):
    def test_motion_manager_start_failure_closes_predecessors_in_reverse(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = StoreFixture(Path(temporary))
            order = []
            capture = _closing("capture", order)
            safety = _closing("safety", order)
            dynamic = _closing("dynamic", order)
            with patch(
                "autospine_workbench.server.P10CaptureJobManager",
                return_value=capture,
            ), patch(
                "autospine_workbench.server.P10SafetyAnalysisManagerV2",
                return_value=safety,
            ), patch(
                "autospine_workbench.server.P10DynamicSeamManagerV2",
                return_value=dynamic,
            ), patch(
                "autospine_workbench.server.P10MotionInstanceV3ManagerV2",
                side_effect=P10MotionInstanceV3ManagerV2Error("private"),
            ):
                with self.assertRaisesRegex(
                    OSError, "P10.6b v2 MotionInstance manager",
                ) as caught:
                    create_server(
                        "127.0.0.1", 0, fixture.workspace,
                        state_root=fixture.state,
                    )
            self.assertNotIn("private", str(caught.exception))
            self.assertEqual(["dynamic", "safety", "capture"], order)
            for manager in (dynamic, safety, capture):
                manager.close.assert_called_once_with()


def _value(status):
    return {"ok": True, "status": status, "run": {"run_id": RUN}}


def _closing(name, order):
    manager = Mock()
    manager.close.side_effect = lambda: order.append(name)
    return manager


if __name__ == "__main__":
    unittest.main()
