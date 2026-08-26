"""Exact P10.2-to-P10.3 admission tests."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.body_sway_preview_inputs import (  # noqa: E402
    BodySwayPreviewInputError,
    require_body_sway_preview_inputs,
)
from tests.body_sway_preview_helpers import BodySwayPreviewFixture  # noqa: E402
from tests.idle_behavior_helpers import IdleBehaviorFixture  # noqa: E402
from autospine_workbench.idle_behavior_candidates import (  # noqa: E402
    compile_idle_behavior_candidates,
)
from autospine_workbench.idle_behavior_decision import (  # noqa: E402
    build_idle_behavior_decision,
)
from autospine_workbench.body_sway_probe_inputs import (  # noqa: E402
    require_body_sway_probe_inputs,
)
from autospine_workbench.body_sway_probe_report import (  # noqa: E402
    compile_body_sway_probe_report,
)
from tests.idle_behavior_decision_helpers import (  # noqa: E402
    adjust_decision,
    completed_review,
)


class BodySwayPreviewInputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.fixture = BodySwayPreviewFixture(Path(cls.temporary.name))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def test_exact_recompiled_report_is_admitted_and_copy_isolated(self):
        value = self.fixture.preview_inputs
        self.assertEqual("manual_visual_required", value.report["status"])
        self.assertEqual(self.fixture.report.sha256, value.report_sha256)
        changed = value.report
        changed["source"].clear()
        self.assertTrue(value.report["source"])
        with self.assertRaises(FrozenInstanceError):
            value._report_json = "{}"  # type: ignore[misc]

    def test_valid_looking_but_stale_report_is_rejected(self):
        report = deepcopy(self.fixture.report.document)
        report["project_id"] = "other-project"
        with self.assertRaisesRegex(
            BodySwayPreviewInputError, "differs from exact"
        ):
            require_body_sway_preview_inputs(
                self.fixture.probe_inputs, report
            )

    def test_structurally_rejected_exact_report_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = IdleBehaviorFixture(Path(temporary))
            candidates = compile_idle_behavior_candidates(
                fixture.manifest, fixture.mesh,
                fixture.retarget, fixture.reviewed,
            ).document
            decision = build_idle_behavior_decision(
                candidates,
                review=completed_review(),
                decisions=[adjust_decision(candidates)],
            ).document
            inputs = require_body_sway_probe_inputs(
                fixture.manifest, candidates, decision,
                fixture.mesh, fixture.retarget, fixture.reviewed,
            )
            report = compile_body_sway_probe_report(inputs)
        self.assertEqual("structural_rejected", report.document["status"])
        with self.assertRaisesRegex(
            BodySwayPreviewInputError, "Structurally rejected"
        ):
            require_body_sway_preview_inputs(inputs, report.document)

    def test_spoofed_probe_input_type_is_rejected_before_replay(self):
        with self.assertRaisesRegex(
            BodySwayPreviewInputError, "exact admitted"
        ):
            require_body_sway_preview_inputs(
                object(), self.fixture.report.document  # type: ignore[arg-type]
            )


if __name__ == "__main__":
    unittest.main()
