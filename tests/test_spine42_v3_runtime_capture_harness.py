"""P10.7b immutable sessions, collector, page, and HTTP boundary tests."""

from __future__ import annotations

import base64
import binascii
from contextlib import contextmanager
from dataclasses import replace
import hashlib
import http.client
import json
from pathlib import Path
import struct
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import zlib

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for candidate in (ROOT, SRC):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))
from autospine_workbench.spine42_runtime_inputs import (  # noqa: E402
    Spine42RuntimePackage,
)
from autospine_workbench.spine42_v3_runtime_capture_collector import (  # noqa: E402
    Spine42V3RuntimeCaptureCollector,
    Spine42V3RuntimeCaptureCollectorError,
)
from autospine_workbench.spine42_v3_runtime_capture_page import (  # noqa: E402
    CAPTURE_CSS, CAPTURE_CSS_SHA256, CAPTURE_JS, CAPTURE_JS_SHA256,
)
from autospine_workbench.spine42_v3_runtime_capture_server import (  # noqa: E402
    create_spine42_v3_runtime_capture_server,
)
from autospine_workbench.spine42_v3_runtime_plan import (  # noqa: E402
    build_spine42_v3_runtime_plan,
)
from autospine_workbench.spine42_v3_runtime_session import (  # noqa: E402
    Spine42V3RuntimeSessionError,
    Spine42V3RuntimeSessions,
    build_spine42_v3_runtime_sessions,
)
from autospine_workbench import spine42_v3_runtime_profile  # noqa: E402
from tests.test_spine42_v3_runtime_plan import _verified  # noqa: E402

RUNTIME_JS = b"fake-official-spine-player"
RUNTIME_CSS = b"fake-official-spine-styles"
RUNTIME_JS_SHA = hashlib.sha256(RUNTIME_JS).hexdigest()
RUNTIME_CSS_SHA = hashlib.sha256(RUNTIME_CSS).hexdigest()

def _runtime(root: Path) -> Spine42RuntimePackage:
    return Spine42RuntimePackage(
        root, root / "player.js", root / "player.css", root / "LICENSE",
        RUNTIME_JS, RUNTIME_CSS, RUNTIME_JS_SHA, RUNTIME_CSS_SHA,
    )

@contextmanager
def _fake_runtime_profile():
    runtime_profile = spine42_v3_runtime_profile._PROFILE["runtime"]
    with patch.dict(runtime_profile, {
        "javascript_sha256": RUNTIME_JS_SHA,
        "stylesheet_sha256": RUNTIME_CSS_SHA,
    }), patch(
        "autospine_workbench.spine42_v3_runtime_session."
        "SPINE_PLAYER_JAVASCRIPT_SHA256",
        RUNTIME_JS_SHA,
    ), patch(
        "autospine_workbench.spine42_v3_runtime_session."
        "SPINE_PLAYER_STYLESHEET_SHA256",
        RUNTIME_CSS_SHA,
    ):
        yield

def _png(width: int = 640, height: int = 640) -> bytes:
    scanlines = (b"\0" + bytes((20, 40, 60, 255)) * width) * height
    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)

    def chunk(kind, payload):
        crc = binascii.crc32(kind)
        crc = binascii.crc32(payload, crc) & 0xFFFFFFFF
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", crc)

    return (
        b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(scanlines)) + chunk(b"IEND", b"")
    )

def _observable_header(value: dict) -> str:
    raw = json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ).encode()
    return base64.b64encode(raw).decode("ascii")

class HarnessFixture:
    def __init__(self, root: Path) -> None:
        self.bundle = _verified()
        self.runtime = _runtime(root / "runtime")
        with _fake_runtime_profile():
            self.plan = build_spine42_v3_runtime_plan(self.bundle)
            self.sessions = build_spine42_v3_runtime_sessions(
                self.bundle, self.runtime, self.plan
            )

class Spine42V3RuntimeCaptureHarnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.fixture = HarnessFixture(Path(cls.temporary.name))
        cls.png = _png()
    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()
    def test_sessions_bind_exact_plan_runtime_assets_and_observables(self):
        sessions = self.fixture.sessions
        self.assertEqual(
            tuple(row["artifact_id"] for row in self.fixture.plan["artifacts"]),
            sessions.artifact_ids,
        )
        opaque = sessions.session(sessions.artifact_ids[0])
        self.assertEqual(
            self.fixture.bundle.bundle_sha256,
            opaque["source"]["bundle_sha256"],
        )
        self.assertEqual(RUNTIME_JS_SHA, opaque["runtime"]["javascript_sha256"])
        self.assertTrue(opaque["expected_observables"]["official_runtime_loaded"])
        self.assertEqual(
            opaque["expected_observables"]["slot_ids"],
            opaque["expected_observables"]["isolation"]["visible_slot_ids"],
        )
        isolate_id = next(
            row["artifact_id"] for row in self.fixture.plan["artifacts"]
            if row["kind"] == "attachment_isolate"
        )
        isolate = sessions.session(isolate_id)
        self.assertEqual(
            [isolate["artifact"]["slot_id"]],
            isolate["expected_observables"]["isolation"]["visible_slot_ids"],
        )
        detached = sessions.document
        detached.clear()
        self.assertTrue(sessions.document)
    def test_sessions_reject_runtime_content_plan_and_crosswire_drift(self):
        changed_runtime = replace(
            self.fixture.runtime, javascript_bytes=b"changed"
        )
        changed_plan = json.loads(json.dumps(self.fixture.plan))
        changed_plan["artifacts"][0]["background"] = "#ffffffff"
        with _fake_runtime_profile():
            with self.assertRaisesRegex(
                Spine42V3RuntimeSessionError, "runtime bytes"
            ):
                build_spine42_v3_runtime_sessions(
                    self.fixture.bundle, changed_runtime, self.fixture.plan
                )
            with self.assertRaisesRegex(
                Spine42V3RuntimeSessionError, "bundle replay"
            ):
                build_spine42_v3_runtime_sessions(
                    self.fixture.bundle, self.fixture.runtime, changed_plan
                )
    def test_collector_requires_exact_inventory_and_complete_ordered_set(self):
        collector = Spine42V3RuntimeCaptureCollector(self.fixture.sessions)
        first = collector.artifact_ids[0]
        observed = collector.session(first)["expected_observables"]
        report = collector.record_capture(
            first, self.png, device_pixel_ratio=1,
            observed_inventory=observed,
        )
        self.assertEqual("captured", report["status"])
        self.assertEqual(first, report["artifact"]["artifact_id"])
        self.assertEqual(observed, report["observables"])
        with self.assertRaises(Spine42V3RuntimeCaptureCollectorError):
            collector.record_capture(
                first, self.png, device_pixel_ratio=1,
                observed_inventory=observed,
            )
        for artifact_id in collector.artifact_ids[1:]:
            collector.record_capture(
                artifact_id, self.png, device_pixel_ratio=1,
                observed_inventory=collector.session(
                    artifact_id
                )["expected_observables"],
            )
        self.assertEqual({
            "expected_artifact_ids", "captured_artifact_ids",
            "error_artifact_ids", "complete",
        }, set(collector.status()))
        self.assertTrue(collector.status()["complete"])
        snapshot = collector.snapshot()
        self.assertEqual(collector.artifact_ids, tuple(snapshot.capture_bytes))
        self.assertEqual(
            collector.artifact_ids,
            tuple(row["artifact"]["artifact_id"] for row in snapshot.reports),
        )
    def test_collector_fails_closed_on_observable_dpr_size_and_error(self):
        artifact_id = self.fixture.sessions.artifact_ids[0]
        expected = self.fixture.sessions.session(
            artifact_id
        )["expected_observables"]
        cases = [
            (self.png, 1, {**expected, "clip_ids": ["wrong"]}),
            (self.png, 2, expected),
            (_png(64, 64), 1, expected),
        ]
        for raw, dpr, observed in cases:
            with self.subTest(dpr=dpr, size=len(raw)):
                collector = Spine42V3RuntimeCaptureCollector(
                    self.fixture.sessions
                )
                with self.assertRaises(Spine42V3RuntimeCaptureCollectorError):
                    collector.record_capture(
                        artifact_id, raw, device_pixel_ratio=dpr,
                        observed_inventory=observed,
                    )
        collector = Spine42V3RuntimeCaptureCollector(self.fixture.sessions)
        collector.record_error(artifact_id, "runtime failed")
        self.assertEqual([artifact_id], collector.status()["error_artifact_ids"])
        with self.assertRaises(Spine42V3RuntimeCaptureCollectorError):
            collector.snapshot()
    def test_page_applies_exact_time_isolation_then_posts_png(self):
        source = CAPTURE_JS.decode()
        self.assertEqual(CAPTURE_JS_SHA256, hashlib.sha256(CAPTURE_JS).hexdigest())
        self.assertEqual(CAPTURE_CSS_SHA256, hashlib.sha256(CAPTURE_CSS).hexdigest())
        required = (
            "entry.trackTime = selectedCase.time_seconds",
            "slot.color.a = 0", "draw: player =>",
            "posedDrawCount >= 2",
            '"X-Autospine-Observed-Inventory"',
            '"Content-Type": "image/png"',
            "official_runtime_loaded: true",
        )
        for marker in required:
            self.assertIn(marker, source)
        self.assertLess(
            source.index("observables = applyIsolation"),
            source.index("poseApplied = true"),
        )

class Spine42V3RuntimeCaptureServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.fixture = HarnessFixture(Path(cls.temporary.name))
        cls.png = _png()
    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()
    def setUp(self) -> None:
        self.collector = Spine42V3RuntimeCaptureCollector(
            self.fixture.sessions
        )
        with _fake_runtime_profile():
            self.server = create_spine42_v3_runtime_capture_server(
                "127.0.0.1", 0, self.fixture.runtime,
                self.fixture.bundle, self.fixture.sessions, self.collector,
            )
        self.thread = threading.Thread(
            target=self.server.serve_forever, daemon=True
        )
        self.thread.start()
        self.host, self.port = self.server.server_address[:2]
    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(5)
    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection(
            self.host, self.port, timeout=5
        )
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        raw = response.read()
        result = response.status, {
            key.lower(): value for key, value in response.getheaders()
        }, raw
        connection.close()
        return result
    def test_get_serves_only_exact_snapshots_session_and_csp_page(self):
        artifact_id = self.collector.artifact_ids[0]
        status, headers, raw = self.request("GET", "/")
        self.assertEqual(307, status)
        self.assertEqual(f"/capture/{artifact_id}", headers["location"])
        expected = {
            "/official/spine-player.min.js": RUNTIME_JS,
            "/runtime/skeleton.json": self.fixture.bundle.document_bytes[
                "skeleton.json"
            ],
            "/capture/harness.js": CAPTURE_JS,
        }
        for path, body in expected.items():
            with self.subTest(path=path):
                status, headers, raw = self.request("GET", path)
                self.assertEqual((200, body), (status, raw))
                self.assertEqual("no-store", headers["cache-control"])
                self.assertIn("default-src 'none'", headers[
                    "content-security-policy"
                ])
        status, _, raw = self.request("GET", f"/api/session/{artifact_id}")
        self.assertEqual(self.collector.session(artifact_id), json.loads(raw))
        status, _, raw = self.request("GET", f"/capture/{artifact_id}")
        self.assertEqual(200, status)
        self.assertIn(f'data-artifact-id="{artifact_id}"'.encode(), raw)
    def test_post_requires_same_origin_and_records_png_observables_once(self):
        artifact_id = self.collector.artifact_ids[0]
        observed = self.collector.session(artifact_id)["expected_observables"]
        headers = {
            "Content-Type": "image/png",
            "Origin": f"http://{self.host}:{self.port}",
            "X-Autospine-Device-Pixel-Ratio": "1",
            "X-Autospine-Observed-Inventory": _observable_header(observed),
        }
        status, _, raw = self.request(
            "POST", f"/api/capture/{artifact_id}", self.png,
            {key: value for key, value in headers.items() if key != "Origin"},
        )
        self.assertEqual((403, "forbidden_origin"), (
            status, json.loads(raw)["error"],
        ))
        status, _, raw = self.request(
            "POST", f"/api/capture/{artifact_id}", self.png, headers
        )
        self.assertEqual(200, status, raw)
        report = json.loads(raw)["report"]
        self.assertEqual(observed, report["observables"])
        self.assertEqual(artifact_id, report["artifact"]["artifact_id"])
        status, _, raw = self.request("GET", "/api/status")
        self.assertEqual(
            [artifact_id], json.loads(raw)["captured_artifact_ids"]
        )

    def test_rejects_foreign_host_bad_inventory_unknown_and_non_loopback(self):
        artifact_id = self.collector.artifact_ids[0]
        status, _, raw = self.request(
            "GET", f"/api/session/{artifact_id}",
            headers={"Host": "attacker.example"},
        )
        self.assertEqual((403, "forbidden_host"), (
            status, json.loads(raw)["error"],
        ))
        headers = {
            "Content-Type": "image/png",
            "Origin": f"http://{self.host}:{self.port}",
            "X-Autospine-Device-Pixel-Ratio": "1",
            "X-Autospine-Observed-Inventory": "not-base64",
        }
        status, _, raw = self.request(
            "POST", f"/api/capture/{artifact_id}", self.png, headers
        )
        self.assertEqual((400, "invalid_capture"), (
            status, json.loads(raw)["error"],
        ))
        status, _, raw = self.request(
            "POST", "/api/capture/missing", self.png, headers
        )
        self.assertEqual((400, "unknown_artifact"), (
            status, json.loads(raw)["error"],
        ))
        with _fake_runtime_profile(), self.assertRaisesRegex(
            ValueError, "loopback"
        ):
            create_spine42_v3_runtime_capture_server(
                "0.0.0.0", 0, self.fixture.runtime, self.fixture.bundle,
                self.fixture.sessions, self.collector,
            )

    def test_crosswired_session_or_collector_is_rejected_before_bind(self):
        document = self.fixture.sessions.document
        document["source"]["bundle_sha256"] = "f" * 64
        forged = Spine42V3RuntimeSessions(json.dumps(
            document, ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":"),
        ))
        with _fake_runtime_profile(), self.assertRaisesRegex(
            ValueError, "input replay"
        ):
            create_spine42_v3_runtime_capture_server(
                "127.0.0.1", 0, self.fixture.runtime,
                self.fixture.bundle, forged, self.collector,
            )

    def test_production_files_stay_bounded(self):
        for name in (
            "spine42_v3_runtime_session.py",
            "spine42_v3_runtime_capture_page.py",
            "spine42_v3_runtime_capture_collector.py",
            "spine42_v3_runtime_capture_server.py",
        ):
            lines = (SRC / "autospine_workbench" / name).read_text(
                encoding="utf-8"
            ).splitlines()
            self.assertLessEqual(len(lines), 300, name)


if __name__ == "__main__":
    unittest.main()
