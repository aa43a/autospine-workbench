"""Public BodySwayRuntimeCapture v1 compilation and validation tests."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover - optional dependency
    Draft202012Validator = None


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for candidate in (ROOT, SRC):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from autospine_workbench.body_sway_runtime_capture import (  # noqa: E402
    BodySwayRuntimeCaptureError,
    compile_body_sway_runtime_capture,
    require_exact_body_sway_runtime_capture,
)
from autospine_workbench.body_sway_runtime_capture_collector import (  # noqa: E402
    BodySwayRuntimeCaptureCollector,
    BodySwayRuntimeCaptureSnapshot,
)
from autospine_workbench.body_sway_runtime_capture_validation import (  # noqa: E402
    BodySwayRuntimeCaptureValidationError,
    require_body_sway_runtime_capture,
)
from autospine_workbench.browser_executable_snapshot import (  # noqa: E402
    BrowserExecutableSnapshot,
)
from autospine_workbench.browser_version_identity import (  # noqa: E402
    browser_version_identity_sha256,
)
from autospine_workbench.spine42_runtime_profile import (  # noqa: E402
    SPINE_PLAYER_JAVASCRIPT_SHA256,
    SPINE_PLAYER_STYLESHEET_SHA256,
)
from tests.body_sway_runtime_capture_helpers import (  # noqa: E402
    RUNTIME_CSS_SHA,
    RUNTIME_JS_SHA,
    RuntimeCaptureFixture,
    capture_png,
    fake_runtime_profile,
)


class BodySwayRuntimeCaptureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)
        cls.fixture = RuntimeCaptureFixture(cls.root)
        cls.png = capture_png()
        cls.browser = BrowserExecutableSnapshot(
            path=str(cls.root / "chrome.exe"),
            family="chromium",
            reported_version="128.0.6613.0",
            version_output_sha256=hashlib.sha256(
                b"Chromium 128.0.6613.0\n"
            ).hexdigest(),
            executable_sha256="b" * 64,
            size_bytes=4096,
        )
        with fake_runtime_profile():
            collector = BodySwayRuntimeCaptureCollector(cls.fixture.sessions)
            for case_id in collector.case_ids:
                collector.record_capture(
                    case_id, cls.png, device_pixel_ratio=1
                )
            cls.snapshot = collector.snapshot()
            cls.capture = compile_body_sway_runtime_capture(
                cls.fixture.preview,
                cls.fixture.runtime,
                cls.fixture.sessions,
                cls.snapshot,
                cls.browser,
            )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def test_compiler_emits_complete_unreviewed_exact_runtime_evidence(self):
        document = self.capture.document
        self._require(document, self.capture.capture_bytes)
        self.assertEqual("captured_unreviewed", document["status"])
        self.assertTrue(
            document["semantics"]["official_runtime_execution_claimed"]
        )
        self.assertFalse(document["semantics"]["human_review_claimed"])
        self.assertFalse(document["semantics"]["release_authority"])
        self.assertEqual(
            self.fixture.preview.sha256,
            document["source"]["temporary_preview_sha256"],
        )
        self.assertEqual(
            self.fixture.sessions.sha256,
            document["source"]["runtime_session_set_sha256"],
        )
        self.assertEqual(19, document["summary"]["case_count"])
        self.assertEqual(
            len(document["cases"]), len(document["artifacts"]["files"])
        )
        self.assertNotIn("path", document["browser"])
        self.assertNotIn("javascript_bytes", document["runtime"])

    def test_compilation_and_exact_replay_are_byte_deterministic(self):
        with fake_runtime_profile():
            second = compile_body_sway_runtime_capture(
                self.fixture.preview, self.fixture.runtime,
                self.fixture.sessions, self.snapshot, self.browser,
            )
            replay_sha = require_exact_body_sway_runtime_capture(
                self.fixture.preview, self.fixture.runtime,
                self.fixture.sessions, self.snapshot, self.browser,
                self.capture.document, self.capture.capture_bytes,
            )
        self.assertEqual(self.capture.canonical_bytes, second.canonical_bytes)
        self.assertEqual(self.capture.capture_bytes, second.capture_bytes)
        self.assertEqual(self.capture.sha256, replay_sha)

    def test_detached_validator_rejects_resealed_overclaims_and_cross_wires(self):
        mutations = []
        visual = self.capture.document
        visual["semantics"]["visual_quality_claimed"] = True
        mutations.append(visual)
        runtime = self.capture.document
        runtime["runtime"]["javascript_sha256"] = "f" * 64
        mutations.append(runtime)
        browser = self.capture.document
        browser["browser"]["reported_version"] = "129.0.6613.0"
        mutations.append(browser)
        browser_sha = self.capture.document
        browser_sha["browser"]["version_output_sha256"] = "0" * 64
        mutations.append(browser_sha)
        cases = self.capture.document
        cases["cases"][1], cases["cases"][3] = (
            cases["cases"][3], cases["cases"][1]
        )
        mutations.append(cases)
        gate = self.capture.document
        gate["release_gate"]["reason_codes"].clear()
        mutations.append(gate)
        for value in mutations:
            with self.subTest(), self.assertRaises(
                BodySwayRuntimeCaptureValidationError
            ):
                self._require(value, self.capture.capture_bytes)

        assets = self.capture.document
        assets["assets"]["texture_sha256"] = "e" * 64
        with fake_runtime_profile(), self.assertRaises(
            BodySwayRuntimeCaptureError
        ):
            require_exact_body_sway_runtime_capture(
                self.fixture.preview, self.fixture.runtime,
                self.fixture.sessions, self.snapshot, self.browser,
                assets, self.capture.capture_bytes,
            )

        resealed_browser = self.capture.document
        resealed_browser["browser"]["reported_version"] = "129.0.6613.0"
        resealed_browser["browser"]["version_output_sha256"] = (
            browser_version_identity_sha256("chromium", "129.0.6613.0")
        )
        with fake_runtime_profile(), self.assertRaises(
            BodySwayRuntimeCaptureError
        ):
            require_exact_body_sway_runtime_capture(
                self.fixture.preview, self.fixture.runtime,
                self.fixture.sessions, self.snapshot, self.browser,
                resealed_browser, self.capture.capture_bytes,
            )

    def test_png_bytes_and_snapshot_reports_are_exactly_bound(self):
        captures = self.capture.capture_bytes
        first = next(iter(captures))
        captures[first] = captures[first][:-1] + b"\x00"
        with self.assertRaises(BodySwayRuntimeCaptureValidationError):
            self._require(self.capture.document, captures)

        reports = list(self.snapshot.reports)
        reports[0]["runtime"]["version"] = "4.2.118"
        forged = BodySwayRuntimeCaptureSnapshot(
            json.dumps(
                reports, ensure_ascii=False, allow_nan=False,
                sort_keys=True, separators=(",", ":"),
            ),
            tuple(self.snapshot.capture_bytes.items()),
        )
        with fake_runtime_profile(), self.assertRaisesRegex(
            BodySwayRuntimeCaptureError, "exact session"
        ):
            compile_body_sway_runtime_capture(
                self.fixture.preview, self.fixture.runtime,
                self.fixture.sessions, forged, self.browser,
            )

    def test_public_accessors_are_copy_isolated(self):
        document = self.capture.document
        document.clear()
        self.assertTrue(self.capture.document)
        captures = self.capture.capture_bytes
        captures.clear()
        self.assertTrue(self.capture.capture_bytes)

    def test_compiler_rejects_non_snapshot_browser(self):
        with fake_runtime_profile(), self.assertRaises(
            BodySwayRuntimeCaptureError
        ):
            compile_body_sway_runtime_capture(
                self.fixture.preview, self.fixture.runtime,
                self.fixture.sessions, self.snapshot, {},
            )

    def test_compiler_rejects_forged_browser_version_identity_sha(self):
        forged = replace(self.browser, version_output_sha256="a" * 64)
        with fake_runtime_profile(), self.assertRaisesRegex(
            BodySwayRuntimeCaptureError, "identity SHA-256"
        ):
            compile_body_sway_runtime_capture(
                self.fixture.preview, self.fixture.runtime,
                self.fixture.sessions, self.snapshot, forged,
            )

    @unittest.skipIf(Draft202012Validator is None, "jsonschema is optional")
    def test_public_document_matches_json_schema(self):
        schema = json.loads((
            ROOT / "schemas" / "body-sway-runtime-capture-v1.schema.json"
        ).read_text("utf-8"))
        Draft202012Validator.check_schema(schema)
        runtime_schema = schema["$defs"]["runtime"]["properties"]
        self.assertEqual(
            SPINE_PLAYER_JAVASCRIPT_SHA256,
            runtime_schema["javascript_sha256"]["const"],
        )
        self.assertEqual(
            SPINE_PLAYER_STYLESHEET_SHA256,
            runtime_schema["stylesheet_sha256"]["const"],
        )
        runtime_schema["javascript_sha256"]["const"] = RUNTIME_JS_SHA
        runtime_schema["stylesheet_sha256"]["const"] = RUNTIME_CSS_SHA
        Draft202012Validator(schema).validate(self.capture.document)

    @staticmethod
    def _require(document, captures):
        with fake_runtime_profile():
            require_body_sway_runtime_capture(document, captures)


if __name__ == "__main__":
    unittest.main()
