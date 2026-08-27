"""P10.7b application-command publication and exact replay tests."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for candidate in (ROOT, SRC):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import autospine_workbench.p10_spine42_v3_runtime_commands as module  # noqa: E402
from autospine_workbench.p10_spine42_v3_runtime_commands import (  # noqa: E402
    P10Spine42V3RuntimeCommandError,
    capture_body_sway_spine42_v3_runtime_command,
    verify_body_sway_spine42_v3_runtime_command,
)
from autospine_workbench.spine42_v3_runtime_store import (  # noqa: E402
    Spine42V3RuntimeStore,
)
from tests.test_spine42_v3_runtime_evidence_store import (  # noqa: E402
    PROJECT,
    RUN_SHA,
    SKELETON_SHA,
    UPSTREAM_SHA,
    _evidence,
)


class P10Spine42V3RuntimeCommandTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.state = Path(self.temporary.name)
        self.evidence = _evidence()

    def tearDown(self):
        self.temporary.cleanup()

    @staticmethod
    def upstream(*, run_sha=RUN_SHA):
        return SimpleNamespace(
            bundle_sha256=UPSTREAM_SHA,
            run_document_sha256=run_sha,
        )

    def test_capture_publishes_reads_back_and_reports_bounded_authority(self):
        run = SimpleNamespace(
            exact_inputs=(object(), object(), object(), object(), object()),
            plan={}, metrics={},
        )
        with patch.object(
            module, "run_spine42_v3_runtime_capture", return_value=run,
        ) as runner, patch.object(
            module, "build_spine42_v3_runtime_evidence",
            return_value=self.evidence,
        ):
            result = capture_body_sway_spine42_v3_runtime_command(
                self.state, PROJECT,
                skeleton_json_sha256=SKELETON_SHA,
                spine42_v3_bundle_sha256=UPSTREAM_SHA,
                runtime_root=Path("runtime"),
                browser_executable=Path("chrome.exe"),
                license_acknowledged=True,
            )
        runner.assert_called_once()
        self.assertEqual("captured", result.mode)
        self.assertEqual("passed", result.metrics_status)
        self.assertEqual("blocked", result.release_gate_status)
        self.assertEqual(3, result.artifact_count)
        self.assertFalse(result.reused)

    def test_historical_verify_replays_the_exact_p10_7a_source(self):
        published = Spine42V3RuntimeStore(self.state).publish(self.evidence)
        with patch.object(
            module.VerifiedSpine42V3BundleReader,
            "load", return_value=self.upstream(),
        ) as replay:
            result = verify_body_sway_spine42_v3_runtime_command(
                self.state, PROJECT,
                spine42_v3_bundle_sha256=UPSTREAM_SHA,
                capture_bundle_sha256=published.capture_bundle_sha256,
            )
        replay.assert_called_once_with(PROJECT, SKELETON_SHA, UPSTREAM_SHA)
        self.assertEqual("verified", result.mode)
        self.assertIsNone(result.reused)

    def test_source_drift_and_missing_address_fail_with_fixed_boundary(self):
        published = Spine42V3RuntimeStore(self.state).publish(self.evidence)
        with patch.object(
            module.VerifiedSpine42V3BundleReader, "load",
            return_value=self.upstream(run_sha="0" * 64),
        ), self.assertRaisesRegex(
            P10Spine42V3RuntimeCommandError, "differs from exact P10.7a",
        ):
            verify_body_sway_spine42_v3_runtime_command(
                self.state, PROJECT,
                spine42_v3_bundle_sha256=UPSTREAM_SHA,
                capture_bundle_sha256=published.capture_bundle_sha256,
            )
        with self.assertRaisesRegex(
            P10Spine42V3RuntimeCommandError, "runtime verification failed",
        ):
            verify_body_sway_spine42_v3_runtime_command(
                self.state, PROJECT,
                spine42_v3_bundle_sha256=UPSTREAM_SHA,
                capture_bundle_sha256="f" * 64,
            )


if __name__ == "__main__":
    unittest.main()
