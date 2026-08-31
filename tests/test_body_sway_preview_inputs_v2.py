"""P10.2b-to-P10.3 v2 exact admission and legacy isolation tests."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for candidate_path in (ROOT, SRC):
    if str(candidate_path) not in sys.path:
        sys.path.insert(0, str(candidate_path))

from autospine_workbench.body_sway_probe_report import (  # noqa: E402
    BodySwayProbeReport,
)
from autospine_workbench.body_sway_preview_inputs import (  # noqa: E402
    BodySwayPreviewInputError,
    require_body_sway_preview_inputs,
)
from autospine_workbench.body_sway_preview_inputs_v2 import (  # noqa: E402
    BodySwayPreviewInputV2Error,
    BodySwayPreviewInputsV2,
    require_body_sway_preview_inputs_v2,
    require_body_sway_preview_world_viewport_v2,
)
from autospine_workbench.capture_framing_candidate import (  # noqa: E402
    CaptureFramingCandidate,
)
from autospine_workbench.capture_framing_history import (  # noqa: E402
    publish_capture_framing_decision,
)
from autospine_workbench.capture_framing_validation import (  # noqa: E402
    CaptureFramingValidationError,
)
from autospine_workbench.capture_framing_verified_head import (  # noqa: E402
    CaptureFramingVerifiedHead,
    read_capture_framing_verified_head,
)
from autospine_workbench.idle_behavior_decision import (  # noqa: E402
    build_idle_behavior_decision,
)
from autospine_workbench.idle_behavior_review_head import (  # noqa: E402
    read_idle_behavior_review_head,
)
from autospine_workbench.idle_behavior_review_store import (  # noqa: E402
    IdleBehaviorReviewStore,
)
from tests.idle_behavior_decision_helpers import (  # noqa: E402
    adjust_decision,
    completed_review,
)
from tests.body_sway_preview_v2_helpers import PreviewV2Fixture  # noqa: E402


class BodySwayPreviewInputsV2Tests(unittest.TestCase):
    def fixture(self, *, action="accept"):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        return PreviewV2Fixture(Path(temporary.name), action=action)

    def test_current_accepted_canvas_only_reject_is_admitted(self):
        fixture = self.fixture()
        value = fixture.admit()
        self.assertIs(type(value), BodySwayPreviewInputsV2)
        self.assertEqual("structural_rejected", value.report["status"])
        self.assertEqual(fixture.report.sha256, value.report_sha256)
        self.assertEqual(fixture.candidate.sha256,
                         value.framing_candidate_sha256)
        self.assertEqual(fixture.framing_decision.sha256,
                         value.framing_decision_sha256)
        self.assertEqual(1, value.framing_revision)
        self.assertEqual(
            fixture.candidate.document["proposed_world_viewport"],
            value.world_viewport,
        )
        self.assertEqual(value.source, value.legacy_projection_inputs().source)

    def test_current_human_adjusted_framing_is_admitted(self):
        fixture = self.fixture(action="adjust")
        value = fixture.admit()
        self.assertEqual("adjust", value.framing_decision["decision"]["action"])
        self.assertEqual(
            "ready_for_temporary_preview_v2",
            value.framing_decision["status"],
        )

    def test_v1_still_rejects_the_same_exact_report(self):
        fixture = self.fixture()
        with self.assertRaisesRegex(
            BodySwayPreviewInputError, "Structurally rejected",
        ):
            require_body_sway_preview_inputs(
                fixture.inputs, fixture.report.document,
            )

    def test_rejected_and_unobservable_heads_are_not_admitted(self):
        for action in ("reject", "unobservable"):
            with self.subTest(action=action):
                fixture = self.fixture(action=action)
                with self.assertRaisesRegex(
                    BodySwayPreviewInputV2Error, "not ready",
                ):
                    fixture.admit()

    def test_stale_p10_1_head_invalidates_candidate(self):
        fixture = self.fixture()
        second = build_idle_behavior_decision(
            fixture.candidates, review=completed_review(2),
            decisions=[adjust_decision(fixture.candidates)],
        )
        IdleBehaviorReviewStore(fixture.state).publish(
            second, fixture.candidates, base_revision=1,
            previous_decision_sha256=fixture.p10_decision.sha256,
        )
        with self.assertRaisesRegex(
            BodySwayPreviewInputV2Error, "current P10.1",
        ):
            fixture.admit()

    def test_stale_framing_head_is_rejected(self):
        fixture = self.fixture()
        stale_decision, stale_history = fixture.current()
        second = fixture._decision(
            "accept", revision=2, previous=stale_decision,
        )
        publish_capture_framing_decision(
            fixture.state, second, fixture.candidate,
            base_revision=1,
            previous_decision_sha256=stale_decision.sha256,
        )
        with self.assertRaisesRegex(
            BodySwayPreviewInputV2Error, "exact current head",
        ):
            fixture.admit(decision=stale_decision, history=stale_history)

    def test_p10_1_head_change_during_admission_fails_closed(self):
        fixture = self.fixture()
        p10_head = read_idle_behavior_review_head(
            fixture.state, fixture.candidates,
        )
        changed = type(p10_head)(
            replace(
                p10_head.snapshot,
                current_revision=p10_head.current_revision + 1,
            ),
            p10_head.decision,
        )
        framing = read_capture_framing_verified_head(
            fixture.state, fixture.candidate,
        )
        target = "autospine_workbench.body_sway_preview_inputs_v2."
        with patch(
            target + "read_idle_behavior_review_head",
            side_effect=[p10_head, changed],
        ), patch(
            target + "read_capture_framing_verified_head",
            side_effect=[framing, framing],
        ), self.assertRaisesRegex(
            BodySwayPreviewInputV2Error, "changed during",
        ):
            fixture.admit()

    def test_framing_head_change_during_admission_fails_closed(self):
        fixture = self.fixture()
        p10_head = read_idle_behavior_review_head(
            fixture.state, fixture.candidates,
        )
        framing = read_capture_framing_verified_head(
            fixture.state, fixture.candidate,
        )
        changed = CaptureFramingVerifiedHead(
            framing.candidate_sha256,
            replace(
                framing.snapshot,
                current_revision=framing.current_revision + 1,
            ),
            framing.decision,
        )
        target = "autospine_workbench.body_sway_preview_inputs_v2."
        with patch(
            target + "read_idle_behavior_review_head",
            side_effect=[p10_head, p10_head],
        ), patch(
            target + "read_capture_framing_verified_head",
            side_effect=[framing, changed],
        ), self.assertRaisesRegex(
            BodySwayPreviewInputV2Error, "changed during",
        ):
            fixture.admit()

    def test_world_viewport_accepts_limit_and_rejects_overflow(self):
        fixture = self.fixture()
        boundary = {
            "x": -500_000_000_000.0,
            "y": -500_000_000_000.0,
            "width": 1_000_000_000_000.0,
            "height": 1_000_000_000_000.0,
        }
        self.assertEqual(
            boundary,
            require_body_sway_preview_world_viewport_v2(
                fixture.candidate, boundary,
            ),
        )
        overflow = dict(boundary)
        overflow["width"] = 1_000_000_000_001.0
        overflow["height"] = 1_000_000_000_001.0
        with self.assertRaisesRegex(
            CaptureFramingValidationError, "invalid",
        ):
            require_body_sway_preview_world_viewport_v2(
                fixture.candidate, overflow,
            )

    def test_report_and_candidate_tampering_are_rejected(self):
        fixture = self.fixture()
        report = deepcopy(fixture.report.document)
        report["selection"]["parameters"]["cycles"] = 3
        tampered_report = BodySwayProbeReport(_canonical(report))
        with self.assertRaises(BodySwayPreviewInputV2Error):
            fixture.admit(report=tampered_report)
        candidate = deepcopy(fixture.candidate.document)
        candidate["proposed_world_viewport"]["x"] += 1.0
        tampered_candidate = CaptureFramingCandidate(_canonical(candidate))
        with self.assertRaises(BodySwayPreviewInputV2Error):
            fixture.admit(candidate=tampered_candidate)


def _canonical(value):
    import json
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      sort_keys=True, separators=(",", ":"))


if __name__ == "__main__":
    unittest.main()
