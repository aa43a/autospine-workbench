"""P10.7b v2 immutable session, collector, and loopback harness tests."""

from __future__ import annotations

import hashlib
import http.client
import json
from dataclasses import replace
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch, PropertyMock


ROOT = Path(__file__).resolve().parents[1]
for item in (ROOT, ROOT / "src"):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from autospine_workbench.spine42_v3_bundle_store_v2 import (  # noqa: E402
    Spine42V3BundleStoreV2,
)
from autospine_workbench.spine42_v3_pipeline_v2 import (  # noqa: E402
    VerifiedSpine42V3PipelineV2,
)
from autospine_workbench.spine42_v3_runtime_capture_collector import (  # noqa: E402
    Spine42V3RuntimeCaptureCollector,
    Spine42V3RuntimeCaptureCollectorError,
)
from autospine_workbench.spine42_v3_runtime_capture_collector_v2 import (  # noqa: E402
    Spine42V3RuntimeCaptureCollectorV2,
    Spine42V3RuntimeCaptureCollectorV2Error,
)
from autospine_workbench.spine42_v3_runtime_capture_page import (  # noqa: E402
    CAPTURE_JS,
)
from autospine_workbench.spine42_v3_runtime_capture_server import (  # noqa: E402
    create_spine42_v3_runtime_capture_server,
)
from autospine_workbench.spine42_v3_runtime_capture_server_v2 import (  # noqa: E402
    create_spine42_v3_runtime_capture_server_v2,
)
from autospine_workbench.spine42_v3_runtime_plan import (  # noqa: E402
    build_spine42_v3_runtime_plan,
)
from autospine_workbench.spine42_v3_runtime_session import (  # noqa: E402
    Spine42V3RuntimeSessionError,
    build_spine42_v3_runtime_sessions,
)
from autospine_workbench.spine42_v3_runtime_session_v2 import (  # noqa: E402
    Spine42V3RuntimeSessionV2Error,
    Spine42V3RuntimeSessionsV2,
    build_spine42_v3_runtime_sessions_v2,
)
from autospine_workbench.spine42_v3_runtime_source_bridge_v2 import (  # noqa: E402
    VerifiedSpine42V3RuntimeSourceBridgeV2,
)
from tests.spine42_v3_v2_helpers import Spine42V3V2Fixture  # noqa: E402
from tests.test_spine42_v3_runtime_capture_harness import (  # noqa: E402
    HarnessFixture, RUNTIME_CSS_SHA, RUNTIME_JS_SHA, _fake_runtime_profile,
    _observable_header, _png, _runtime,
)


HEADS = (
    "autospine_workbench.spine42_v3_current_heads_v2."
    "require_current_body_sway_dynamic_seam_heads_v2"
)
SESSION_V2 = "autospine_workbench.spine42_v3_runtime_session_v2"


class V2HarnessFixture:
    def __init__(self, root: Path):
        self.source_fixture = Spine42V3V2Fixture(root)
        with self.source_fixture.pipeline_sources():
            compilation = VerifiedSpine42V3PipelineV2(
                self.source_fixture.state_root
            ).build_from_verified(self.source_fixture.motion_bundle)
        observation = self.source_fixture.motion_fixture.observation
        with patch(HEADS, return_value=observation):
            self.bundle = Spine42V3BundleStoreV2(
                self.source_fixture.motion_fixture.capture,
                self.source_fixture.motion_fixture.project_store,
            ).publish(
                compilation, self.source_fixture.motion_bundle, observation,
            ).verified_bundle
        self.runtime = _runtime(root / "runtime")
        with _fake_runtime_profile_v2():
            self.source = VerifiedSpine42V3RuntimeSourceBridgeV2(
                self.source_fixture.state_root
            ).build_from_verified(self.bundle)
            self.sessions = build_spine42_v3_runtime_sessions_v2(
                self.bundle, self.runtime, self.source,
            )


class Spine42V3RuntimeCaptureHarnessV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        root = Path(cls.temporary.name)
        cls.fixture = V2HarnessFixture(root / "v2")
        cls.v1 = HarnessFixture(root / "v1")
        cls.png = _png()

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_v1_session_literals_survive_shared_core_extraction(self):
        sessions = self.v1.sessions
        first = sessions.session(sessions.artifact_ids[0])
        encoded = json.dumps(
            first, ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":"),
        ).encode()
        self.assertEqual(
            "d5d8c5fed5db3faf9679ded1111df9b74a3b935aaef525eae5e844b1a81f47ce",
            sessions.sha256,
        )
        self.assertEqual(
            "8132c84e0a49b3514e2b14d52fd5d2f58cc6e14f789256ba502ad0c51da2a857",
            hashlib.sha256(encoded).hexdigest(),
        )

    def test_v2_sessions_bind_admission_plan_runtime_assets_and_order(self):
        sessions = self.fixture.sessions
        source = self.fixture.source
        self.assertEqual(2, sessions.document["format_version"])
        self.assertEqual(source.admission, sessions.source_admission)
        self.assertEqual(
            source.admission_sha256,
            sessions.document["source_admission_sha256"],
        )
        self.assertEqual(
            tuple(row["artifact_id"] for row in source.plan["artifacts"]),
            sessions.artifact_ids,
        )
        first = sessions.session(sessions.artifact_ids[0])
        self.assertEqual(2, first["format_version"])
        self.assertEqual(source.admission_sha256,
                         first["source_admission_sha256"])
        self.assertEqual(RUNTIME_JS_SHA,
                         first["runtime"]["javascript_sha256"])
        self.assertEqual(
            self.fixture.bundle.skeleton_json_sha256,
            first["assets"]["skeleton_sha256"],
        )
        self.assertNotEqual(self.v1.sessions.sha256, sessions.sha256)

    def test_v1_v2_types_are_rejected_in_both_directions(self):
        with _fake_runtime_profile_v2(), self.assertRaises(
            Spine42V3RuntimeSessionV2Error
        ):
            build_spine42_v3_runtime_sessions_v2(
                self.v1.bundle, self.fixture.runtime, self.fixture.source,
            )
        with _fake_runtime_profile(), self.assertRaises(
            Spine42V3RuntimeSessionError
        ):
            build_spine42_v3_runtime_sessions(
                self.fixture.bundle, self.v1.runtime,
                build_spine42_v3_runtime_plan(self.v1.bundle),
            )
        with self.assertRaises(Spine42V3RuntimeCaptureCollectorError):
            Spine42V3RuntimeCaptureCollector(self.fixture.sessions)
        with self.assertRaises(Spine42V3RuntimeCaptureCollectorV2Error):
            Spine42V3RuntimeCaptureCollectorV2(self.v1.sessions)

    def test_runtime_asset_plan_and_admission_tamper_fail_closed(self):
        changed_runtime = replace(
            self.fixture.runtime, javascript_bytes=b"changed",
        )
        with _fake_runtime_profile_v2(), self.assertRaisesRegex(
            Spine42V3RuntimeSessionV2Error, "runtime bytes"
        ):
            build_spine42_v3_runtime_sessions_v2(
                self.fixture.bundle, changed_runtime, self.fixture.source,
            )

        raw = self.fixture.bundle.document_bytes
        raw["skeleton.png"] += b"tamper"
        with _fake_runtime_profile_v2(), patch.object(
            type(self.fixture.bundle), "document_bytes",
            new_callable=PropertyMock, return_value=raw,
        ), self.assertRaisesRegex(
            Spine42V3RuntimeSessionV2Error, "asset bytes"
        ):
            build_spine42_v3_runtime_sessions_v2(
                self.fixture.bundle, self.fixture.runtime,
                self.fixture.source,
            )

        for name in ("plan", "admission"):
            value = getattr(self.fixture.source, name)
            value["format_version"] = 99
            with self.subTest(name=name), _fake_runtime_profile_v2(), \
                    patch.object(
                        type(self.fixture.source), name,
                        new_callable=PropertyMock, return_value=value,
                    ), self.assertRaises(Spine42V3RuntimeSessionV2Error):
                build_spine42_v3_runtime_sessions_v2(
                    self.fixture.bundle, self.fixture.runtime,
                    self.fixture.source,
                )

    def test_v2_collector_returns_complete_ordered_png_snapshot(self):
        collector = Spine42V3RuntimeCaptureCollectorV2(
            self.fixture.sessions
        )
        for artifact_id in collector.artifact_ids:
            observed = collector.session(artifact_id)["expected_observables"]
            collector.record_capture(
                artifact_id, self.png, device_pixel_ratio=1,
                observed_inventory=observed,
            )
        self.assertTrue(collector.status()["complete"])
        snapshot = collector.snapshot()
        self.assertEqual(collector.artifact_ids,
                         tuple(snapshot.capture_bytes))
        self.assertEqual(
            collector.artifact_ids,
            tuple(row["artifact"]["artifact_id"]
                  for row in snapshot.reports),
        )

    def test_v2_server_serves_exact_bytes_and_enforces_local_boundary(self):
        collector = Spine42V3RuntimeCaptureCollectorV2(
            self.fixture.sessions
        )
        with _fake_runtime_profile_v2():
            server = create_spine42_v3_runtime_capture_server_v2(
                "127.0.0.1", 0, self.fixture.runtime,
                self.fixture.bundle, self.fixture.source,
                self.fixture.sessions, collector,
            )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        host, port = server.server_address[:2]
        try:
            status, headers, raw = _request(host, port, "GET",
                                             "/runtime/skeleton.json")
            self.assertEqual(200, status)
            self.assertEqual(
                self.fixture.bundle.document_bytes["skeleton.json"], raw,
            )
            self.assertIn("frame-ancestors 'none'",
                          headers["content-security-policy"])
            status, _, _ = _request(
                host, port, "GET", "/runtime/skeleton.json?remote=1",
            )
            self.assertEqual(404, status)
            status, _, _ = _request(
                host, port, "GET", "/runtime/%2e%2e/skeleton.json",
            )
            self.assertEqual(404, status)
            artifact = collector.artifact_ids[0]
            status, _, raw = _request(
                host, port, "GET", f"/api/session/{artifact}",
            )
            self.assertEqual(2, json.loads(raw)["format_version"])
            status, _, raw = _request(
                host, port, "GET", f"/api/session/{artifact}",
                headers={"Host": "attacker.example"},
            )
            self.assertEqual((403, "forbidden_host"),
                             (status, json.loads(raw)["error"]))
            observed = collector.session(artifact)["expected_observables"]
            capture_headers = {
                "Content-Type": "image/png",
                "Origin": f"http://{host}:{port}",
                "X-Autospine-Device-Pixel-Ratio": "1",
                "X-Autospine-Observed-Inventory": (
                    _observable_header(observed)
                ),
            }
            status, _, raw = _request(
                host, port, "POST", f"/api/capture/{artifact}",
                self.png, {key: value for key, value in capture_headers.items()
                           if key != "Origin"},
            )
            self.assertEqual((403, "forbidden_origin"),
                             (status, json.loads(raw)["error"]))
            status, _, _ = _request(
                host, port, "POST", f"/api/capture/{artifact}",
                self.png, capture_headers,
            )
            self.assertEqual(200, status)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(5)
        with _fake_runtime_profile_v2(), self.assertRaisesRegex(
            ValueError, "loopback"
        ):
            create_spine42_v3_runtime_capture_server_v2(
                "0.0.0.0", 0, self.fixture.runtime,
                self.fixture.bundle, self.fixture.source,
                self.fixture.sessions,
                Spine42V3RuntimeCaptureCollectorV2(self.fixture.sessions),
            )

    def test_servers_reject_cross_version_session_and_collector(self):
        with _fake_runtime_profile_v2(), self.assertRaises(ValueError):
            create_spine42_v3_runtime_capture_server_v2(
                "127.0.0.1", 0, self.fixture.runtime,
                self.fixture.bundle, self.fixture.source, self.v1.sessions,
                Spine42V3RuntimeCaptureCollector(self.v1.sessions),
            )
        with _fake_runtime_profile(), self.assertRaises(ValueError):
            create_spine42_v3_runtime_capture_server(
                "127.0.0.1", 0, self.v1.runtime, self.v1.bundle,
                self.fixture.sessions,
                Spine42V3RuntimeCaptureCollectorV2(self.fixture.sessions),
            )

    def test_v2_server_rejects_resealed_session_tamper(self):
        document = self.fixture.sessions.document
        document["source_admission"]["authority"][
            "official_runtime_loaded"
        ] = True
        forged = Spine42V3RuntimeSessionsV2(json.dumps(
            document, ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":"),
        ))
        collector = Spine42V3RuntimeCaptureCollectorV2(forged)
        with _fake_runtime_profile_v2(), self.assertRaisesRegex(
            ValueError, "exact input replay"
        ):
            create_spine42_v3_runtime_capture_server_v2(
                "127.0.0.1", 0, self.fixture.runtime,
                self.fixture.bundle, self.fixture.source, forged, collector,
            )


def _fake_runtime_profile_v2():
    stack = _fake_runtime_profile()
    constants = patch.multiple(
        SESSION_V2,
        SPINE_PLAYER_JAVASCRIPT_SHA256=RUNTIME_JS_SHA,
        SPINE_PLAYER_STYLESHEET_SHA256=RUNTIME_CSS_SHA,
    )

    class Both:
        def __enter__(self):
            stack.__enter__()
            constants.__enter__()
            return self

        def __exit__(self, *args):
            constants.__exit__(*args)
            return stack.__exit__(*args)

    return Both()


def _request(host, port, method, path, body=None, headers=None):
    connection = http.client.HTTPConnection(host, port, timeout=5)
    connection.request(method, path, body=body, headers=headers or {})
    response = connection.getresponse()
    raw = response.read()
    result = response.status, {
        key.lower(): value for key, value in response.getheaders()
    }, raw
    connection.close()
    return result


if __name__ == "__main__":
    unittest.main()
