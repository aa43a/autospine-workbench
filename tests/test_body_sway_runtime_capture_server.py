"""HTTP boundary tests for the dedicated P10.3b capture server."""

from __future__ import annotations

import hashlib
import http.client
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for candidate in (ROOT, SRC):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from autospine_workbench.body_sway_runtime_capture_collector import (  # noqa: E402
    BodySwayRuntimeCaptureCollector,
)
from autospine_workbench.body_sway_runtime_capture_page import (  # noqa: E402
    CAPTURE_JS,
)
from autospine_workbench.body_sway_runtime_capture_server import (  # noqa: E402
    create_body_sway_runtime_capture_server,
)
from autospine_workbench.body_sway_runtime_capture_session import (  # noqa: E402
    BodySwayRuntimeCaptureSessions,
)
from tests.body_sway_runtime_capture_helpers import (  # noqa: E402
    RUNTIME_CSS,
    RUNTIME_JS,
    RuntimeCaptureFixture,
    capture_png,
    fake_runtime_profile,
)


class BodySwayRuntimeCaptureServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.fixture = RuntimeCaptureFixture(Path(cls.temporary.name))
        cls.png = capture_png()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def setUp(self) -> None:
        with fake_runtime_profile():
            self.collector = BodySwayRuntimeCaptureCollector(
                self.fixture.sessions
            )
            self.server = create_body_sway_runtime_capture_server(
                "127.0.0.1",
                0,
                self.fixture.runtime,
                self.fixture.preview,
                self.fixture.sessions,
                self.collector,
            )
        self.thread = threading.Thread(
            target=self.server.serve_forever, daemon=True
        )
        self.thread.start()
        self.host, self.port = self.server.server_address[:2]

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def request(
        self,
        method: str,
        path: str,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, str], bytes]:
        connection = http.client.HTTPConnection(
            self.host, self.port, timeout=5
        )
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        raw = response.read()
        result = (
            response.status,
            {key.lower(): value for key, value in response.getheaders()},
            raw,
        )
        connection.close()
        return result

    def test_get_serves_exact_snapshots_sessions_and_capture_page(self) -> None:
        status, headers, raw = self.request("GET", "/")
        self.assertEqual(307, status)
        self.assertEqual("/runtime/player.html", headers["location"])
        self.assertEqual(b"", raw)

        expected = {
            "/runtime/player.html": self.fixture.preview.artifact_bytes[
                "runtime/player.html"
            ],
            "/runtime/skeleton.json": self.fixture.preview.artifact_bytes[
                "runtime/skeleton.json"
            ],
            "/official/spine-player.min.js": RUNTIME_JS,
            "/official/spine-player.min.css": RUNTIME_CSS,
            "/capture/harness.js": CAPTURE_JS,
        }
        for path, body in expected.items():
            with self.subTest(path=path):
                status, headers, raw = self.request("GET", path)
                self.assertEqual(200, status)
                self.assertEqual(body, raw)
                self.assertEqual("no-store", headers["cache-control"])
                self.assertEqual("nosniff", headers["x-content-type-options"])
                self.assertIn(
                    "default-src 'none'", headers["content-security-policy"]
                )
                self.assertIn(
                    "script-src 'self'", headers["content-security-policy"]
                )

        status, _, raw = self.request("GET", "/api/session/setup")
        self.assertEqual(200, status)
        self.assertEqual(self.collector.session("setup"), json.loads(raw))
        status, _, raw = self.request("GET", "/capture/setup")
        self.assertEqual(200, status)
        self.assertIn(b'data-case-id="setup"', raw)
        self.assertIn(b'/official/spine-player.min.js', raw)

    def test_head_has_get_metadata_without_a_response_body(self) -> None:
        for path in (
            "/runtime/skeleton.png",
            "/official/spine-player.min.js",
            "/api/session/setup",
            "/capture/setup",
        ):
            with self.subTest(path=path):
                get_status, get_headers, get_raw = self.request("GET", path)
                status, headers, raw = self.request("HEAD", path)
                self.assertEqual(get_status, status)
                self.assertEqual(str(len(get_raw)), headers["content-length"])
                self.assertEqual(get_headers["content-type"], headers["content-type"])
                self.assertIn("connect-src 'self'", headers[
                    "content-security-policy"
                ])
                self.assertEqual(b"", raw)

    def test_valid_png_capture_is_recorded_once(self) -> None:
        headers = self.capture_headers()
        status, _, raw = self.request(
            "POST", "/api/capture/setup", self.png,
            {key: value for key, value in headers.items() if key != "Origin"},
        )
        self.assertEqual(403, status)
        self.assertEqual("forbidden_origin", json.loads(raw)["error"])
        status, _, raw = self.request(
            "POST", "/api/capture/setup", self.png, headers
        )
        self.assertEqual(200, status, raw)
        result = json.loads(raw)
        self.assertTrue(result["ok"])
        report = result["report"]
        self.assertEqual("captured", report["status"])
        self.assertEqual("setup", report["case"]["id"])
        self.assertEqual(640, report["image"]["width"])
        self.assertEqual(
            hashlib.sha256(self.png).hexdigest(),
            report["image"]["png_sha256"],
        )

        status, _, raw = self.request("GET", "/api/status")
        self.assertEqual(200, status)
        state = json.loads(raw)
        self.assertEqual(["setup"], state["captured_case_ids"])
        self.assertFalse(state["complete"])
        status, _, raw = self.request(
            "POST", "/api/capture/setup", self.png, headers
        )
        self.assertEqual(400, status)
        self.assertEqual("invalid_capture", json.loads(raw)["error"])

    def test_rejects_wrong_dpr_foreign_host_origin_and_unknown_case(self) -> None:
        status, _, raw = self.request(
            "GET", "/api/session/setup", headers={"Host": "attacker.example"}
        )
        self.assertEqual(403, status)
        self.assertEqual("forbidden_host", json.loads(raw)["error"])

        headers = self.capture_headers()
        status, _, raw = self.request(
            "POST",
            "/api/capture/setup",
            self.png,
            {**headers, "Origin": "https://attacker.example"},
        )
        self.assertEqual(403, status)
        self.assertEqual("forbidden_origin", json.loads(raw)["error"])
        status, _, raw = self.request(
            "POST",
            "/api/capture/setup",
            self.png,
            {**headers, "X-Autospine-Device-Pixel-Ratio": "2"},
        )
        self.assertEqual(400, status)
        self.assertEqual("invalid_capture", json.loads(raw)["error"])
        status, _, raw = self.request(
            "POST", "/api/capture/not-a-case", self.png, headers
        )
        self.assertEqual(400, status)
        self.assertEqual("unknown_case", json.loads(raw)["error"])
        self.assertEqual([], self.collector.status()["captured_case_ids"])

    def test_cross_wired_collector_is_rejected_before_binding(self) -> None:
        document = self.fixture.sessions.document
        document["source"]["temporary_preview_sha256"] = "f" * 64
        forged = BodySwayRuntimeCaptureSessions(json.dumps(
            document, ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":"),
        ))
        with fake_runtime_profile():
            collector = BodySwayRuntimeCaptureCollector(forged)
            with self.assertRaisesRegex(ValueError, "cross-wired"):
                create_body_sway_runtime_capture_server(
                    "127.0.0.1", 0, self.fixture.runtime,
                    self.fixture.preview, self.fixture.sessions, collector,
                )

    def test_refuses_non_loopback_binding(self) -> None:
        with self.assertRaisesRegex(ValueError, "loopback"):
            create_body_sway_runtime_capture_server(
                "0.0.0.0",
                0,
                self.fixture.runtime,
                self.fixture.preview,
                self.fixture.sessions,
                self.collector,
            )

    def capture_headers(self) -> dict[str, str]:
        return {
            "Content-Type": "image/png",
            "Origin": f"http://{self.host}:{self.port}",
            "X-Autospine-Device-Pixel-Ratio": "1",
        }


if __name__ == "__main__":
    unittest.main()
