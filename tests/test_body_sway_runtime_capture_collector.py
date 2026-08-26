"""P10.3b session and in-memory capture collector tests."""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.body_sway_runtime_capture_collector import (  # noqa: E402
    BodySwayRuntimeCaptureCollector,
    BodySwayRuntimeCaptureCollectorError,
)
from autospine_workbench.body_sway_runtime_capture_session import (  # noqa: E402
    BodySwayRuntimeCaptureSessionError,
    BodySwayRuntimeCaptureSessions,
    build_body_sway_runtime_capture_sessions,
)
from autospine_workbench.body_sway_preview_profile import (  # noqa: E402
    CAPTURE_PLAN_DIGEST_DOMAIN,
)
from autospine_workbench.png_rgba import decode_rgba_png  # noqa: E402
from autospine_workbench.resolved_project import canonical_sha256  # noqa: E402
from tests.body_sway_runtime_capture_helpers import (  # noqa: E402
    RUNTIME_CSS_SHA,
    RUNTIME_JS_SHA,
    RuntimeCaptureFixture,
    capture_png,
    fake_runtime_profile,
)


class BodySwayRuntimeCaptureCollectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.fixture = RuntimeCaptureFixture(Path(cls.temporary.name))
        cls.png = capture_png()

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_sessions_bind_preview_runtime_and_exact_capture_plan(self):
        sessions = self.fixture.sessions
        cases = self.fixture.preview.document["capture_plan"]["cases"]
        self.assertEqual(
            [row["case_id"] for row in cases], list(sessions.case_ids)
        )
        first = sessions.session("setup")
        self.assertEqual(
            self.fixture.preview.sha256,
            first["source"]["temporary_preview_sha256"],
        )
        self.assertEqual(RUNTIME_JS_SHA, first["runtime"]["javascript_sha256"])
        self.assertEqual(RUNTIME_CSS_SHA, first["runtime"]["stylesheet_sha256"])
        self.assertIsNone(first["case"]["animation"])
        collector = BodySwayRuntimeCaptureCollector(sessions)
        detached = collector.session("setup")
        detached["case"].clear()
        self.assertTrue(collector.session("setup")["case"])

    def test_runtime_content_must_equal_its_pinned_hashes(self):
        changed = replace(
            self.fixture.runtime, javascript_bytes=b"changed-runtime"
        )
        with fake_runtime_profile(), self.assertRaisesRegex(
            BodySwayRuntimeCaptureSessionError, "runtime bytes"
        ):
            build_body_sway_runtime_capture_sessions(
                self.fixture.preview, changed
            )

    def test_complete_capture_set_is_ordered_frozen_and_copy_isolated(self):
        collector = BodySwayRuntimeCaptureCollector(self.fixture.sessions)
        for case_id in collector.case_ids:
            report = collector.record_capture(
                case_id, self.png, device_pixel_ratio=1
            )
            self.assertEqual("captured", report["status"])
        self.assertTrue(collector.status()["complete"])
        snapshot = collector.snapshot()
        self.assertEqual(collector.case_ids, tuple(
            row["case"]["id"] for row in snapshot.reports
        ))
        self.assertEqual(len(collector.case_ids), len(snapshot.capture_bytes))
        changed = snapshot.capture_bytes
        changed.clear()
        self.assertTrue(snapshot.capture_bytes)
        reports = snapshot.reports
        reports[0].clear()
        self.assertTrue(snapshot.reports[0])

    def test_duplicate_wrong_dpr_size_total_limit_and_error_fail_closed(self):
        collector = BodySwayRuntimeCaptureCollector(self.fixture.sessions)
        case_id = collector.case_ids[0]
        with self.assertRaises(BodySwayRuntimeCaptureCollectorError):
            collector.record_capture(case_id, self.png, device_pixel_ratio=2)
        with self.assertRaises(BodySwayRuntimeCaptureCollectorError):
            collector.record_capture(
                case_id, capture_png(64, 64), device_pixel_ratio=1
            )
        with patch(
            "autospine_workbench.body_sway_runtime_capture_collector."
            "MAX_CAPTURE_TOTAL_BYTES",
            len(self.png) - 1,
        ), self.assertRaisesRegex(
            BodySwayRuntimeCaptureCollectorError, "total byte"
        ):
            collector.record_capture(case_id, self.png, device_pixel_ratio=1)
        collector.record_error(case_id, "runtime failed")
        with self.assertRaises(BodySwayRuntimeCaptureCollectorError):
            collector.record_capture(case_id, self.png, device_pixel_ratio=1)
        with self.assertRaises(BodySwayRuntimeCaptureCollectorError):
            collector.snapshot()

    def test_complete_plan_and_shared_profile_mutations_fail_closed(self):
        mutations = []
        missing = self.fixture.sessions.document
        del missing["capture_plan"]["cases"][-2:]
        self._reseal_plan(missing)
        mutations.append(missing)
        reordered = self.fixture.sessions.document
        cases = reordered["capture_plan"]["cases"]
        cases[1:3], cases[3:5] = cases[3:5], cases[1:3]
        self._reseal_plan(reordered)
        mutations.append(reordered)
        wrong_profile = self.fixture.sessions.document
        wrong_profile["capture_plan"]["background"] = "#ffffffff"
        self._reseal_plan(wrong_profile)
        mutations.append(wrong_profile)
        bogus_runtime = self.fixture.sessions.document
        bogus_runtime["runtime"] = {"bogus": True}
        mutations.append(bogus_runtime)
        for value in mutations:
            with self.subTest(), self.assertRaises(
                BodySwayRuntimeCaptureCollectorError
            ):
                BodySwayRuntimeCaptureCollector(self._session_set(value))
        with self.assertRaises(BodySwayRuntimeCaptureCollectorError):
            BodySwayRuntimeCaptureCollector({})

    def test_dimensions_are_preflighted_and_concurrent_decode_is_bounded(self):
        collector = BodySwayRuntimeCaptureCollector(self.fixture.sessions)
        with patch(
            "autospine_workbench.body_sway_runtime_capture_collector."
            "decode_rgba_png"
        ) as decoder, self.assertRaisesRegex(
            BodySwayRuntimeCaptureCollectorError, "dimensions"
        ):
            collector.record_capture(
                collector.case_ids[0], capture_png(64, 64),
                device_pixel_ratio=1,
            )
        decoder.assert_not_called()

        started, release = threading.Event(), threading.Event()
        failures = []

        def slow_decode(raw, *, source_name):
            started.set()
            release.wait(5)
            return decode_rgba_png(raw, source_name=source_name)

        def first_capture():
            try:
                collector.record_capture(
                    collector.case_ids[0], self.png, device_pixel_ratio=1
                )
            except Exception as exc:  # pragma: no cover - assertion below
                failures.append(exc)

        with patch(
            "autospine_workbench.body_sway_runtime_capture_collector."
            "decode_rgba_png",
            side_effect=slow_decode,
        ):
            thread = threading.Thread(target=first_capture)
            thread.start()
            self.assertTrue(started.wait(5))
            with self.assertRaisesRegex(
                BodySwayRuntimeCaptureCollectorError, "already being decoded"
            ):
                collector.record_capture(
                    collector.case_ids[1], self.png, device_pixel_ratio=1
                )
            release.set()
            thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertEqual([], failures)

    @staticmethod
    def _session_set(document):
        return BodySwayRuntimeCaptureSessions(json.dumps(
            document, ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":"),
        ))

    @staticmethod
    def _reseal_plan(document):
        plan = document["capture_plan"]
        plan.pop("capture_plan_sha256", None)
        digest = canonical_sha256({
            "domain": CAPTURE_PLAN_DIGEST_DOMAIN, **plan,
        })
        plan["capture_plan_sha256"] = digest
        document["source"]["capture_plan_sha256"] = digest
        document["summary"]["case_count"] = len(plan["cases"])


if __name__ == "__main__":
    unittest.main()
