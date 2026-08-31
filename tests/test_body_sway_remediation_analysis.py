"""Shared exact-schedule P10.2 remediation integration tests."""

from __future__ import annotations

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

from autospine_workbench.body_sway_probe_geometry import (  # noqa: E402
    evaluate_prepared_body_sway_geometry_sample,
)
from autospine_workbench.body_sway_probe_inputs import (  # noqa: E402
    require_body_sway_probe_inputs,
)
from autospine_workbench.body_sway_probe_report import (  # noqa: E402
    compile_body_sway_probe_report,
)
from autospine_workbench.body_sway_remediation_analysis import (  # noqa: E402
    compile_body_sway_remediation_analysis,
)
from autospine_workbench.idle_behavior_candidates import (  # noqa: E402
    compile_idle_behavior_candidates,
)
from autospine_workbench.idle_behavior_decision import (  # noqa: E402
    build_idle_behavior_decision,
)
from tests.idle_behavior_decision_helpers import (  # noqa: E402
    adjust_decision,
    completed_review,
)
from tests.idle_behavior_helpers import IdleBehaviorFixture  # noqa: E402


class BodySwayRemediationAnalysisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.fixture = IdleBehaviorFixture(Path(cls.temporary.name))
        candidates = compile_idle_behavior_candidates(
            cls.fixture.manifest, cls.fixture.mesh,
            cls.fixture.retarget, cls.fixture.reviewed,
        ).document
        decision = build_idle_behavior_decision(
            candidates, review=completed_review(),
            decisions=[adjust_decision(candidates)],
        ).document
        cls.inputs = require_body_sway_probe_inputs(
            cls.fixture.manifest, candidates, decision,
            cls.fixture.mesh, cls.fixture.retarget, cls.fixture.reviewed,
        )

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_one_geometry_replay_feeds_viewport_and_all_affected_regions(self):
        report = compile_body_sway_probe_report(self.inputs)
        original = report.canonical_bytes
        target = "autospine_workbench.body_sway_remediation_analysis."
        with patch(
            target + "evaluate_prepared_body_sway_geometry_sample",
            wraps=evaluate_prepared_body_sway_geometry_sample,
        ) as evaluator:
            first = compile_body_sway_remediation_analysis(
                self.inputs, report,
            )
        second = compile_body_sway_remediation_analysis(self.inputs, report)
        count = report.document["schedule"]["sample_count"]
        self.assertEqual(count, evaluator.call_count)
        self.assertEqual(original, report.canonical_bytes)
        self.assertEqual(
            first.dynamic_viewport.canonical_bytes,
            second.dynamic_viewport.canonical_bytes,
        )
        viewport = first.dynamic_viewport.document
        self.assertEqual("fitted", viewport["fit_status"])
        self.assertEqual(count, viewport["source"]["sample_count"])
        self.assertGreater(viewport["source"]["point_count"], 0)
        self.assertTrue(first.rebind_candidates)
        self.assertEqual(
            [row.document["source"]["attachment_id"]
             for row in first.rebind_candidates],
            sorted(row.document["source"]["attachment_id"]
                   for row in first.rebind_candidates),
        )
        for row in first.rebind_candidates:
            document = row.document
            self.assertEqual("candidate_only", document["status"])
            self.assertEqual(count, document["source"]["motion_sample_count"])
            self.assertFalse(document["semantics"]["release_authority"])


if __name__ == "__main__":
    unittest.main()
