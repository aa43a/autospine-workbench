"""Server lifecycle regression for the independent P10.7b v2 API."""

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
for item in (ROOT, ROOT / "src"):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from autospine_workbench.p10_spine42_v3_runtime_http_security_v2 import (  # noqa: E402
    INTENT,
)
from autospine_workbench.p10_spine42_v3_runtime_manager_v2 import (  # noqa: E402
    P10Spine42V3RuntimeManagerV2Error,
)
from autospine_workbench.server import create_server  # noqa: E402
from tests.test_project_store import StoreFixture  # noqa: E402


A, B, C = (character * 64 for character in "abc")
PREFIX = "/api/p10/spine42-v3-runtime-v2"


class P10Spine42V3RuntimeV2ServerIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.fixture = StoreFixture(Path(self.temporary.name))
        self.close_order = []
        names = ("capture", "safety", "dynamic", "motion", "spine", "runtime")
        managers = [self._manager(name) for name in names]
        (self.capture, self.safety, self.dynamic, self.motion,
         self.spine, self.runtime) = managers
        self.runtime.catalog.return_value = _catalog()
        self.runtime.get.return_value = {"job_id": C, "status": "running"}
        self.runtime.submit.return_value = {"job_id": C, "status": "queued"}
        classes = (
            "P10CaptureJobManager", "P10SafetyAnalysisManagerV2",
            "P10DynamicSeamManagerV2", "P10MotionInstanceV3ManagerV2",
            "P10Spine42V3ManagerV2", "P10Spine42V3RuntimeManagerV2",
        )
        self.patches = [
            patch(f"autospine_workbench.server.{name}", return_value=manager)
            for name, manager in zip(classes, managers)
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
        connection = http.client.HTTPConnection(self.host, self.port, timeout=5)
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
            "X-Autospine-Intent": INTENT,
        }

    def test_get_head_and_options_are_zero_write_delegations(self):
        status, _, value = self.request(
            "GET", f"{PREFIX}/candidates?spine_run_id={C}",
            headers={"Sec-Fetch-Site": "same-origin"},
        )
        self.assertEqual(200, status)
        self.assertEqual("automatic", value["selection"]["mode"])
        self.runtime.catalog.assert_called_once_with(C)

        status, headers, raw = self.request(
            "HEAD", f"{PREFIX}/jobs/{C}",
            headers={"Sec-Fetch-Site": "same-origin"},
        )
        self.assertEqual(200, status)
        self.assertEqual(b"", raw)
        self.assertIn("content-length", headers)
        self.runtime.get.assert_called_once_with(C)
        self.runtime.submit.assert_not_called()

        before = tuple(self.runtime.method_calls)
        for path, allow in (
            (f"{PREFIX}/candidates", "GET, HEAD, OPTIONS"),
            (f"{PREFIX}/jobs", "POST, OPTIONS"),
            (f"{PREFIX}/jobs/{C}", "GET, HEAD, OPTIONS"),
        ):
            status, headers, raw = self.request("OPTIONS", path)
            self.assertEqual(204, status)
            self.assertEqual(allow, headers["allow"])
            self.assertEqual(b"", raw)
        self.assertEqual(before, tuple(self.runtime.method_calls))

    def test_post_derives_selection_and_returns_accepted_snapshot(self):
        automatic = _payload(A, B, "auth-http-auto")
        status, _, value = self.request(
            "POST", f"{PREFIX}/jobs", automatic, self.mutation_headers(),
        )
        self.assertEqual(202, status)
        self.assertEqual("queued", value["status"])
        self.runtime.submit.assert_called_with(
            automatic, selection_source="automatic",
        )

        explicit = _payload(C, B, "auth-http-explicit")
        self.request(
            "POST", f"{PREFIX}/jobs", explicit, self.mutation_headers(),
        )
        self.runtime.submit.assert_called_with(
            explicit, selection_source="explicit",
        )

    def test_bad_query_headers_body_and_manager_errors_are_path_free(self):
        status, _, value = self.request(
            "GET", f"{PREFIX}/candidates?spine_run_id={C}&again={C}",
        )
        self.assertEqual((400, "invalid_runtime_v2_query"),
                         (status, value["error"]))

        status, _, value = self.request(
            "POST", f"{PREFIX}/jobs", _payload(),
            {"Origin": f"http://{self.host}:{self.port}"},
        )
        self.assertEqual(403, status)
        self.assertTrue(value["error"].startswith("forbidden_"))

        malformed = _payload(); malformed["selection_source"] = "automatic"
        status, _, value = self.request(
            "POST", f"{PREFIX}/jobs", malformed, self.mutation_headers(),
        )
        self.assertEqual((400, "invalid_runtime_v2_request"),
                         (status, value["error"]))

        self.runtime.get.side_effect = P10Spine42V3RuntimeManagerV2Error(
            str(self.fixture.state / "private"),
        )
        status, _, value = self.request("GET", f"{PREFIX}/jobs/{C}")
        self.assertEqual((404, "runtime_v2_job_not_found"),
                         (status, value["error"]))
        self.assertNotIn(str(self.fixture.state), repr(value))

    def test_wrong_methods_use_independent_family_policy(self):
        for method, path, allow in (
            ("GET", f"{PREFIX}/jobs", "POST, OPTIONS"),
            ("POST", f"{PREFIX}/candidates", "GET, HEAD, OPTIONS"),
            ("PUT", f"{PREFIX}/jobs/{C}", "GET, HEAD, OPTIONS"),
            ("PATCH", f"{PREFIX}/jobs", "POST, OPTIONS"),
        ):
            with self.subTest(method=method, path=path):
                status, headers, value = self.request(method, path, {})
                self.assertEqual(405, status)
                self.assertEqual(allow, headers["allow"])
                self.assertEqual("method_not_allowed", value["error"])

    def test_server_close_is_reverse_dependency_order(self):
        self._close_server()
        self.assertEqual(
            ["runtime", "spine", "motion", "dynamic", "safety", "capture"],
            self.close_order,
        )
        for manager in (
            self.runtime, self.spine, self.motion, self.dynamic,
            self.safety, self.capture,
        ):
            manager.close.assert_called_once_with()


class P10Spine42V3RuntimeV2StartupTests(unittest.TestCase):
    def test_runtime_manager_failure_closes_every_predecessor_in_reverse(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = StoreFixture(Path(temporary))
            order = []
            managers = [_closing(name, order) for name in (
                "capture", "safety", "dynamic", "motion", "spine",
            )]
            classes = (
                "P10CaptureJobManager", "P10SafetyAnalysisManagerV2",
                "P10DynamicSeamManagerV2", "P10MotionInstanceV3ManagerV2",
                "P10Spine42V3ManagerV2",
            )
            patches = [
                patch(f"autospine_workbench.server.{name}", return_value=manager)
                for name, manager in zip(classes, managers)
            ]
            patches.append(patch(
                "autospine_workbench.server.P10Spine42V3RuntimeManagerV2",
                side_effect=P10Spine42V3RuntimeManagerV2Error("private"),
            ))
            for current in patches:
                current.start()
            try:
                with self.assertRaisesRegex(
                    OSError, "P10.7b v2 Runtime manager",
                ) as caught:
                    create_server(
                        "127.0.0.1", 0, fixture.workspace,
                        state_root=fixture.state,
                    )
            finally:
                for current in reversed(patches):
                    current.stop()
            self.assertNotIn("private", str(caught.exception))
            self.assertEqual(
                ["spine", "motion", "dynamic", "safety", "capture"], order,
            )


def _catalog():
    return {"selection": {
        "mode": "automatic", "recommended_candidate_id": A,
        "recommended_entry_sha256": B,
    }, "candidates": []}


def _payload(candidate=A, entry=B, authorization="auth-http-0001"):
    return {
        "candidate_id": candidate, "entry_sha256": entry,
        "authorization_id": authorization, "retry_of_job_id": None,
        "explicit_runtime_license_confirmation": True,
        "explicit_run_confirmation": True,
    }


def _closing(name, order):
    manager = Mock()
    manager.close.side_effect = lambda: order.append(name)
    return manager


if __name__ == "__main__":
    unittest.main()
