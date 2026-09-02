"""Linear session projection and capture-boundary regression tests."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
for item in (ROOT, ROOT / "src"):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

import autospine_workbench.spine42_v3_runtime_capture_core as capture_core  # noqa: E402
import autospine_workbench.spine42_v3_runtime_session_core as session_core  # noqa: E402
from autospine_workbench.spine42_v3_runtime_capture_collector import (  # noqa: E402
    Spine42V3RuntimeCaptureCollector,
    Spine42V3RuntimeCaptureCollectorError,
)
from autospine_workbench.spine42_v3_runtime_capture_collector_v2 import (  # noqa: E402
    Spine42V3RuntimeCaptureCollectorV2,
)
from autospine_workbench.spine42_v3_runtime_capture_server import (  # noqa: E402
    create_spine42_v3_runtime_capture_server,
)
from autospine_workbench.spine42_v3_runtime_session_v2 import (  # noqa: E402
    Spine42V3RuntimeSessionsV2,
)
from tests.test_spine42_v3_runtime_capture_harness import (  # noqa: E402
    HarnessFixture, _fake_runtime_profile, _png,
)


CASE_COUNT = 55
ATTACHMENT_COUNT = 32
ARTIFACT_COUNT = CASE_COUNT * (2 + ATTACHMENT_COUNT)


class Spine42V3RuntimeSessionScalingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.fixture = HarnessFixture(Path(cls.temporary.name))

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_maximum_inventory_is_parsed_once_and_projected_linearly(self):
        original_loads = json.loads
        with patch.object(
            session_core.json, "loads", wraps=original_loads,
        ) as document_loads:
            sessions = Spine42V3RuntimeSessionsV2(_maximum_session_set())
        self.assertEqual(1, document_loads.call_count)
        self.assertEqual(ARTIFACT_COUNT, len(sessions.artifact_ids))

        detached = sessions.session_bytes
        first = sessions.artifact_ids[0]
        detached[first] = b"{}"
        self.assertEqual(first, sessions.session(first)["artifact"][
            "artifact_id"
        ])

        with patch.object(
            capture_core.json, "loads", wraps=original_loads,
        ) as session_loads:
            collector = Spine42V3RuntimeCaptureCollectorV2(sessions)
        self.assertEqual(ARTIFACT_COUNT, session_loads.call_count)
        self.assertEqual(sessions.artifact_ids, collector.artifact_ids)
        self.assertFalse(hasattr(collector, "_captures"))

    def test_v1_server_preserves_collector_first_error_boundary(self):
        with _fake_runtime_profile(), self.assertRaisesRegex(
            ValueError, "^Spine v3 runtime collector type is invalid$"
        ):
            create_spine42_v3_runtime_capture_server(
                "127.0.0.1", 0, object(), object(), object(), object(),
            )
        collector = Spine42V3RuntimeCaptureCollector(self.fixture.sessions)
        with _fake_runtime_profile(), self.assertRaisesRegex(
            ValueError, "Runtime session set type is invalid"
        ):
            create_spine42_v3_runtime_capture_server(
                "127.0.0.1", 0, object(), object(), object(), collector,
            )

    def test_snapshot_rejects_v1_private_capture_sha_drift(self):
        collector = Spine42V3RuntimeCaptureCollector(self.fixture.sessions)
        png = _png()
        for artifact_id in collector.artifact_ids:
            observed = collector.session(artifact_id)[
                "expected_observables"
            ]
            collector.record_capture(
                artifact_id, png, device_pixel_ratio=1,
                observed_inventory=observed,
            )
        first = collector.artifact_ids[0]
        raw = collector._captures[first]
        collector._captures[first] = raw[:-1] + bytes((raw[-1] ^ 1,))
        with self.assertRaisesRegex(
            Spine42V3RuntimeCaptureCollectorError, "report SHA"
        ):
            collector.snapshot()


def _maximum_session_set() -> str:
    slots = [f"slot-{index:02d}" for index in range(ATTACHMENT_COUNT)]
    artifacts, cases = [], []
    for case_index in range(CASE_COUNT):
        case_id = f"case-{case_index:03d}"
        artifact_ids = []
        for suffix, kind, slot in (
            ("opaque", "opaque_composite", None),
            ("alpha", "transparent_composite", None),
            *((f"isolate-{index:02d}", "attachment_isolate", name)
              for index, name in enumerate(slots)),
        ):
            artifact_id = f"{case_id}.{suffix}"
            artifact_ids.append(artifact_id)
            artifacts.append({
                "artifact_id": artifact_id, "case_id": case_id,
                "kind": kind, "slot_id": slot,
                "attachment_id": slot, "path": f"{artifact_id}.png",
                "background": "#00000000",
            })
        cases.append({"case_id": case_id, "artifact_ids": artifact_ids})
    admission = {"admission_sha256": "a" * 64}
    document = {
        "format": "autospine-spine42-v3-runtime-session-set",
        "format_version": 2, "source": {}, "runtime": {}, "assets": {},
        "plan_sha256": "b" * 64,
        "plan": {
            "capture": {
                "viewport": {"width": 640, "height": 640},
                "device_pixel_ratio": 1, "preserve_drawing_buffer": True,
            },
            "cases": cases, "artifacts": artifacts,
        },
        "artifact_ids": [row["artifact_id"] for row in artifacts],
        "runtime_inventory": {
            "clip_ids": ["idle"], "slot_ids": slots,
            "attachments": [
                {"slot_id": slot, "attachment_id": slot} for slot in slots
            ],
        },
        "source_admission_sha256": admission["admission_sha256"],
        "source_admission": admission,
        "summary": {
            "case_count": CASE_COUNT, "artifact_count": ARTIFACT_COUNT,
        },
    }
    return json.dumps(
        document, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    )


if __name__ == "__main__":
    unittest.main()
