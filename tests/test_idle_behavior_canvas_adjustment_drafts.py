"""Exact, authority-free P10.2 to P10.1 draft handoff tests."""

from __future__ import annotations

from copy import deepcopy
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

from autospine_workbench.body_sway_probe_application import (
    BodySwayProbeApplicationHeadChanged,
)
from autospine_workbench.body_sway_derived_cache import (
    BodySwayDerivedCache,
)
from autospine_workbench.idle_behavior_canvas_adjustment_drafts import (
    FORMAT,
    FORMAT_VERSION,
    IdleBehaviorCanvasAdjustmentDraftApplication,
    IdleBehaviorCanvasAdjustmentDraftNotFound,
    IdleBehaviorCanvasAdjustmentDraftStale,
)


class IdleBehaviorCanvasAdjustmentDraftTests(unittest.TestCase):
    package_id = "a" * 64
    adjustment_sha = "b" * 64
    candidate_sha = "c" * 64
    decision_sha = "d" * 64

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.state_root = Path(self.temporary.name) / "state"
        self.state_root.mkdir()
        self.application = IdleBehaviorCanvasAdjustmentDraftApplication(
            self.state_root,
        )
        self.proposal = {
            "candidate_id": "body-sway-canvas-adjustment-" + "e" * 64,
            "status": "unvalidated_draft",
            "authority": "none",
            "parameters": {"cycles": 2},
        }
        self.document = {
            "source": {
                "current_p10_1_head": {
                    "candidate_sha256": self.candidate_sha,
                    "decision_sha256": self.decision_sha,
                    "revision": 2,
                },
            },
            "adjustment_candidates": [self.proposal],
        }
        self.probe = {
            "package": {"package_id": self.package_id},
            "candidate_sha256": self.candidate_sha,
            "history": {
                "current_revision": 2,
                "head_decision_sha256": self.decision_sha,
            },
            "canvas_adjustment": {
                "candidate_sha256": self.adjustment_sha,
                "document": self.document,
            },
        }
        self.entry = {
            "package": {"package_id": self.package_id},
            "candidate_sha256": self.candidate_sha,
            "history": {
                "current_revision": 2,
                "head_decision_sha256": self.decision_sha,
            },
        }

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _prepare(self, *, probe=None, entry=None):
        probe = self.probe if probe is None else probe
        entry = self.entry if entry is None else entry
        with patch(
            "autospine_workbench.idle_behavior_canvas_adjustment_drafts."
            "BodySwayProbeApplication.prepare",
            return_value=probe,
        ) as probe_prepare, patch(
            "autospine_workbench.idle_behavior_canvas_adjustment_drafts."
            "IdleBehaviorReviewApplication.prepare",
            return_value=entry,
        ) as review_prepare:
            result = self.application.prepare(
                self.package_id,
                self.adjustment_sha,
                project_ids=("fixture-project",),
            )
        return result, probe_prepare, review_prepare

    def test_success_returns_one_exact_zero_authority_draft(self):
        result, probe_prepare, review_prepare = self._prepare()

        self.assertEqual(FORMAT, result["format"])
        self.assertEqual(FORMAT_VERSION, result["format_version"])
        self.assertEqual("unvalidated_draft", result["status"])
        self.assertIs(result["entry"], self.entry)
        self.assertIs(result["proposal"], self.proposal)
        self.assertEqual(
            self.adjustment_sha,
            result["canvas_adjustment"]["candidate_sha256"],
        )
        probe_prepare.assert_called_once_with(
            self.package_id, project_ids=("fixture-project",),
        )
        review_prepare.assert_called_once_with(
            self.package_id, project_ids=("fixture-project",),
        )

    def test_invalid_sha_is_rejected_before_any_exact_replay(self):
        with patch(
            "autospine_workbench.idle_behavior_canvas_adjustment_drafts."
            "BodySwayProbeApplication.prepare",
        ) as probe_prepare, self.assertRaises(
            IdleBehaviorCanvasAdjustmentDraftNotFound,
        ):
            self.application.prepare(self.package_id, "not-a-sha")
        probe_prepare.assert_not_called()

    def test_no_single_candidate_is_not_found(self):
        probe = deepcopy(self.probe)
        probe["canvas_adjustment"]["document"][
            "adjustment_candidates"
        ] = []
        with patch(
            "autospine_workbench.idle_behavior_canvas_adjustment_drafts."
            "BodySwayProbeApplication.prepare",
            return_value=probe,
        ), patch(
            "autospine_workbench.idle_behavior_canvas_adjustment_drafts."
            "IdleBehaviorReviewApplication.prepare",
        ) as review_prepare, self.assertRaises(
            IdleBehaviorCanvasAdjustmentDraftNotFound,
        ):
            self.application.prepare(self.package_id, self.adjustment_sha)
        review_prepare.assert_not_called()

    def test_valid_but_different_adjustment_sha_is_not_found(self):
        with patch(
            "autospine_workbench.idle_behavior_canvas_adjustment_drafts."
            "BodySwayProbeApplication.prepare",
            return_value=self.probe,
        ), patch(
            "autospine_workbench.idle_behavior_canvas_adjustment_drafts."
            "IdleBehaviorReviewApplication.prepare",
        ) as review_prepare, self.assertRaises(
            IdleBehaviorCanvasAdjustmentDraftNotFound,
        ):
            self.application.prepare(self.package_id, "f" * 64)
        review_prepare.assert_not_called()

    def test_entry_or_probe_head_drift_is_stale(self):
        cases = []
        entry_revision = deepcopy(self.entry)
        entry_revision["history"]["current_revision"] = 3
        cases.append((self.probe, entry_revision))
        entry_decision = deepcopy(self.entry)
        entry_decision["history"]["head_decision_sha256"] = "f" * 64
        cases.append((self.probe, entry_decision))
        probe_revision = deepcopy(self.probe)
        probe_revision["history"]["current_revision"] = 3
        cases.append((probe_revision, self.entry))
        probe_decision = deepcopy(self.probe)
        probe_decision["history"]["head_decision_sha256"] = "f" * 64
        cases.append((probe_decision, self.entry))
        probe_candidate = deepcopy(self.probe)
        probe_candidate["candidate_sha256"] = "f" * 64
        cases.append((probe_candidate, self.entry))
        foreign_probe = deepcopy(self.probe)
        foreign_entry = deepcopy(self.entry)
        foreign_probe["package"]["package_id"] = "f" * 64
        foreign_entry["package"]["package_id"] = "f" * 64
        cases.append((foreign_probe, foreign_entry))

        for probe, entry in cases:
            with self.subTest(probe=probe, entry=entry), self.assertRaises(
                IdleBehaviorCanvasAdjustmentDraftStale,
            ):
                self._prepare(probe=probe, entry=entry)

    def test_probe_head_change_is_normalized_to_stale(self):
        with patch(
            "autospine_workbench.idle_behavior_canvas_adjustment_drafts."
            "BodySwayProbeApplication.prepare",
            side_effect=BodySwayProbeApplicationHeadChanged("private"),
        ), self.assertRaises(
            IdleBehaviorCanvasAdjustmentDraftStale,
        ):
            self.application.prepare(self.package_id, self.adjustment_sha)

    def test_injected_cache_is_forwarded_to_detail_replay(self):
        cache = BodySwayDerivedCache()
        application = IdleBehaviorCanvasAdjustmentDraftApplication(
            self.state_root, derived_cache=cache,
        )
        with patch(
            "autospine_workbench.idle_behavior_canvas_adjustment_drafts."
            "BodySwayProbeApplication"
        ) as probe_class, patch(
            "autospine_workbench.idle_behavior_canvas_adjustment_drafts."
            "IdleBehaviorReviewApplication.prepare",
            return_value=self.entry,
        ):
            probe_class.return_value.prepare.return_value = self.probe
            result = application.prepare(
                self.package_id, self.adjustment_sha,
            )
        probe_class.assert_called_once_with(
            self.state_root, derived_cache=cache,
        )
        self.assertEqual("unvalidated_draft", result["status"])


if __name__ == "__main__":
    unittest.main()
