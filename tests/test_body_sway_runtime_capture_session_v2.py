"""Exact Preview v2 official-runtime session and collector tests."""

from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for candidate in (ROOT, SRC):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from autospine_workbench.body_sway_runtime_capture_collector import (  # noqa: E402
    BodySwayRuntimeCaptureCollector,
    BodySwayRuntimeCaptureCollectorError,
)
from autospine_workbench.body_sway_runtime_capture_session_v2 import (  # noqa: E402
    BodySwayRuntimeCaptureSessionV2Error,
    BodySwayRuntimeCaptureSessionsV2,
    build_body_sway_runtime_capture_sessions_v2,
    require_exact_body_sway_runtime_capture_sessions_v2,
)
from autospine_workbench.body_sway_runtime_capture_session_v2_validation import (  # noqa: E402
    BodySwayRuntimeCaptureSessionV2ValidationError,
    require_body_sway_runtime_capture_session_set_v2,
)
from autospine_workbench.resolved_project import canonical_sha256  # noqa: E402
from autospine_workbench.temporary_body_sway_preview_v2 import (  # noqa: E402
    compile_temporary_body_sway_preview_v2,
)
from tests.body_sway_runtime_capture_helpers import (  # noqa: E402
    RUNTIME_CSS_SHA,
    RUNTIME_JS_SHA,
    capture_png,
    fake_runtime,
)
from tests.body_sway_preview_v2_helpers import PreviewV2Fixture  # noqa: E402
from tests.test_temporary_body_sway_preview_v2 import (  # noqa: E402
    _patched_source,
    _source_images,
)


PACKAGE_JSON_SHA = "a" * 64
LICENSE_SHA = "b" * 64


@contextmanager
def _fake_v2_runtime_profile():
    targets = (
        "autospine_workbench.body_sway_runtime_capture_session_v2",
        "autospine_workbench.body_sway_runtime_capture_session_v2_validation",
    )
    with patch(targets[0] + ".SPINE_PLAYER_JAVASCRIPT_SHA256",
               RUNTIME_JS_SHA), \
            patch(targets[0] + ".SPINE_PLAYER_STYLESHEET_SHA256",
                  RUNTIME_CSS_SHA), \
            patch(targets[1] + ".SPINE_PLAYER_JAVASCRIPT_SHA256",
                  RUNTIME_JS_SHA), \
            patch(targets[1] + ".SPINE_PLAYER_STYLESHEET_SHA256",
                  RUNTIME_CSS_SHA):
        yield


class BodySwayRuntimeCaptureSessionV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        root = Path(cls.temporary.name)
        cls.fixture = PreviewV2Fixture(root)
        cls.inputs = cls.fixture.admit()
        cls.images = _source_images(cls.fixture.fixture.mesh.rig)
        with _patched_source(cls.images):
            cls.preview = compile_temporary_body_sway_preview_v2(
                cls.inputs, cls.fixture.fixture.mesh,
            )
        cls.runtime = replace(
            fake_runtime(root / "runtime"),
            package_json_sha256=PACKAGE_JSON_SHA,
            license_sha256=LICENSE_SHA,
        )
        with _fake_v2_runtime_profile():
            cls.sessions = build_body_sway_runtime_capture_sessions_v2(
                cls.preview, cls.runtime,
            )

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_sessions_bind_every_preview_framing_runtime_and_case_identity(self):
        document = self.sessions.document
        preview = self.preview.document
        source = document["source"]
        self.assertEqual(2, document["format_version"])
        self.assertEqual(self.preview.sha256,
                         source["temporary_preview_v2_sha256"])
        self.assertEqual(self.preview.artifact_set_sha256,
                         source["preview_artifact_set_sha256"])
        self.assertEqual(preview["projection"], document["projection"])
        self.assertEqual(preview["capture_plan"], document["capture_plan"])
        self.assertEqual(canonical_sha256(preview["source"]),
                         source["preview_source_sha256"])
        self.assertEqual(preview["source"]["current_p10_1_head"],
                         source["current_p10_1_head"])
        self.assertEqual(
            preview["source"]["body_sway_probe_report_sha256"],
            source["body_sway_probe_report_sha256"],
        )
        self.assertEqual(preview["projection"]["world_viewport"],
                         source["world_viewport"])
        self.assertEqual(PACKAGE_JSON_SHA,
                         document["runtime"]["package_json_sha256"])
        self.assertEqual(LICENSE_SHA,
                         document["runtime"]["license_sha256"])
        self.assertFalse(document["runtime"]
                         ["license_file_presence_is_authorization"])
        self.assertNotIn("license_acknowledged", document["runtime"])
        self.assertEqual(
            [row["case_id"] for row in preview["capture_plan"]["cases"]],
            list(self.sessions.case_ids),
        )
        case = self.sessions.session("setup")
        self.assertEqual(2, case["format_version"])
        self.assertIsNone(case["case"]["animation"])
        case["source"].clear()
        self.assertTrue(self.sessions.session("setup")["source"])

    def test_build_is_deterministic_detached_valid_and_exactly_replayable(self):
        with _fake_v2_runtime_profile():
            second = build_body_sway_runtime_capture_sessions_v2(
                self.preview, self.runtime,
            )
            require_body_sway_runtime_capture_session_set_v2(
                self.sessions.document,
            )
            replayed = require_exact_body_sway_runtime_capture_sessions_v2(
                self.preview, self.runtime, self.sessions,
            )
        self.assertEqual(self.sessions.canonical_bytes,
                         second.canonical_bytes)
        self.assertEqual(self.sessions.sha256, replayed.sha256)

    def test_structural_cross_bindings_fail_closed(self):
        mutations = (
            lambda row: row["source"].update({
                "preview_projection_v2_sha256": "0" * 64,
            }),
            lambda row: row["source"]["world_viewport"].update({
                "x": row["source"]["world_viewport"]["x"] + 1,
            }),
            lambda row: row["projection"].update({
                "capture_framing_revision":
                    row["projection"]["capture_framing_revision"] + 1,
            }),
            lambda row: row["capture_plan"]["cases"].pop(),
            lambda row: row["sample_ticks"].pop(),
            lambda row: row["assets"].update({"atlas_sha256": "invalid"}),
            lambda row: row["runtime"].update({"license_sha256": "invalid"}),
        )
        for mutate in mutations:
            changed = self.sessions.document
            mutate(changed)
            with self.subTest(mutate=mutate), _fake_v2_runtime_profile(), \
                    self.assertRaises(
                        BodySwayRuntimeCaptureSessionV2ValidationError,
                    ):
                require_body_sway_runtime_capture_session_set_v2(changed)

    def test_exact_replay_rejects_valid_digest_tampering(self):
        changed = self.sessions.document
        changed["source"]["temporary_preview_v2_sha256"] = "0" * 64
        forged = BodySwayRuntimeCaptureSessionsV2(_canonical(changed))
        with _fake_v2_runtime_profile():
            require_body_sway_runtime_capture_session_set_v2(forged.document)
            with self.assertRaisesRegex(
                BodySwayRuntimeCaptureSessionV2Error, "exact replay",
            ):
                require_exact_body_sway_runtime_capture_sessions_v2(
                    self.preview, self.runtime, forged,
                )

    def test_package_and_license_digests_are_mandatory(self):
        for field in ("package_json_sha256", "license_sha256"):
            changed = replace(self.runtime, **{field: ""})
            with self.subTest(field=field), _fake_v2_runtime_profile(), \
                    self.assertRaisesRegex(
                        BodySwayRuntimeCaptureSessionV2Error,
                        "package.json and LICENSE",
                    ):
                build_body_sway_runtime_capture_sessions_v2(
                    self.preview, changed,
                )

    def test_collector_strictly_accepts_v2_and_records_exact_session(self):
        with _fake_v2_runtime_profile():
            collector = BodySwayRuntimeCaptureCollector(self.sessions)
        case_id = collector.case_ids[0]
        report = collector.record_capture(
            case_id, capture_png(), device_pixel_ratio=1,
        )
        self.assertEqual("captured", report["status"])
        self.assertEqual(2, collector.session(case_id)["format_version"])
        self.assertEqual(self.sessions.sha256,
                         report["session_set_sha256"])
        self.assertFalse(collector.status()["complete"])
        with self.assertRaises(BodySwayRuntimeCaptureCollectorError):
            BodySwayRuntimeCaptureCollector(
                _DuckSessionSet(self.sessions.document),
            )


class _DuckSessionSet:
    def __init__(self, document):
        self.document = deepcopy(document)


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      sort_keys=True, separators=(",", ":"))


if __name__ == "__main__":
    unittest.main()
