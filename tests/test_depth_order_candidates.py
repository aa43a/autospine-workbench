"""Candidate-only depth-order Schmitt evidence tests."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover
    Draft202012Validator = None

from autospine_workbench.depth_order_candidate_validation import (  # noqa: E402
    DepthOrderCandidateValidationError,
    require_depth_order_candidates,
)
from autospine_workbench.depth_order_candidates import (  # noqa: E402
    compile_depth_order_candidates,
)
from autospine_workbench.depth_order_inputs import (  # noqa: E402
    require_depth_order_inputs,
)
from tests.depth_order_helpers import DepthOrderFixture  # noqa: E402


class DepthOrderCandidateTests(unittest.TestCase):
    def compile(self, *, degrees=60.0, depth="away_from_camera"):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        fixture = DepthOrderFixture(
            Path(temporary.name), head_degrees=degrees,
            depth_positive=depth,
        )
        inputs = require_depth_order_inputs(
            fixture.projected, fixture.retarget, fixture.mesh
        )
        policy = fixture.policy(inputs)
        result = compile_depth_order_candidates(
            fixture.projected, fixture.retarget, fixture.mesh, policy
        )
        return fixture, inputs, policy, result

    def test_jitter_below_enter_threshold_emits_no_event(self):
        _fixture, _inputs, _policy, result = self.compile(degrees=20.0)
        pair = result.document["pairs"][0]
        self.assertEqual([], pair["events"])
        self.assertTrue(all(
            row["current_front_slot"] == "face" for row in pair["samples"]
        ))

    def test_sustained_crossing_emits_exactly_one_reviewable_candidate(self):
        fixture, inputs, policy, result = self.compile()
        document = result.document
        pair = document["pairs"][0]
        self.assertEqual(1, len(pair["events"]))
        event = pair["events"][0]
        self.assertEqual(("face", "leg"), (
            event["from_front_slot"], event["to_front_slot"]
        ))
        self.assertEqual({
            "start_source_frame_index": 1,
            "end_source_frame_index": 2,
            "start_tick": 33333,
            "end_tick": 66667,
            "sample_count": 2,
        }, event["evidence_window"])
        self.assertEqual("switch_candidate", pair["samples"][2]["state"])
        self.assertEqual("candidate_only", document["semantics"]["mode"])
        self.assertEqual("review_required",
                         document["semantics"]["apply_policy"])
        self.assertFalse(document["semantics"]["decision_emitted"])
        self.assertEqual("bone-segment-midpoint",
                         document["semantics"]["proxy_quality"])
        self.assertFalse(document["semantics"]["raster_truth_claimed"])
        self.assertFalse(document["semantics"]["runtime_timeline_emitted"])
        require_depth_order_candidates(
            document, policy=policy, inputs=inputs
        )
        self.assertEqual([], fixture.retarget.motion_instance.get("draw_order", []))

    def test_depth_positive_flip_reverses_score_and_prevents_false_switch(self):
        _a, _ai, _ap, away = self.compile(depth="away_from_camera")
        _t, _ti, _tp, toward = self.compile(depth="toward_camera")
        away_pair, toward_pair = (
            away.document["pairs"][0], toward.document["pairs"][0]
        )
        away_score = away_pair["samples"][1]["scores"][0]["front_score"]
        toward_score = toward_pair["samples"][1]["scores"][0]["front_score"]
        self.assertAlmostEqual(-away_score, toward_score)
        self.assertEqual(1, len(away_pair["events"]))
        self.assertEqual([], toward_pair["events"])

    def test_stale_source_and_derived_score_tamper_fail(self):
        _fixture, inputs, policy, result = self.compile()
        stale = result.document
        stale["source"]["p3"]["rig_sha256"] = "f" * 64
        with self.assertRaisesRegex(
            DepthOrderCandidateValidationError, "stale"
        ):
            require_depth_order_candidates(
                stale, policy=policy, inputs=inputs
            )
        tampered = result.document
        tampered["pairs"][0]["samples"][1]["scores"][0]["front_score"] += 1
        with self.assertRaisesRegex(
            DepthOrderCandidateValidationError, "score math"
        ):
            require_depth_order_candidates(tampered)

    @unittest.skipIf(Draft202012Validator is None, "install test extra")
    def test_schema_is_valid_and_accepts_candidates(self):
        _fixture, _inputs, _policy, result = self.compile()
        schema = json.loads((
            ROOT / "schemas" / "depth-order-candidates-v1.schema.json"
        ).read_text("utf-8"))
        Draft202012Validator.check_schema(schema)
        self.assertEqual(
            [], list(Draft202012Validator(schema).iter_errors(result.document))
        )


if __name__ == "__main__":
    unittest.main()
