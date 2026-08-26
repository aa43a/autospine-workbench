"""P9.4 exhaustive human decision contract tests."""

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

from autospine_workbench.motion_policy_candidate_inventory import (  # noqa: E402
    MotionPolicyCandidateInventoryError,
    derive_motion_policy_candidates,
)
from autospine_workbench.motion_policy_decision import (  # noqa: E402
    MotionPolicyDecisionError,
    build_motion_policy_decision,
)
from autospine_workbench.motion_policy_decision_validation import (  # noqa: E402
    MotionPolicyDecisionValidationError,
    require_motion_policy_decision,
)
from tests.motion_policy_decision_helpers import (  # noqa: E402
    MotionPolicyDecisionFixture,
    approved_review,
)

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover - optional test extra
    Draft202012Validator = None


class MotionPolicyDecisionTests(unittest.TestCase):
    def fixture(self, **kwargs) -> MotionPolicyDecisionFixture:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        return MotionPolicyDecisionFixture(Path(temporary.name), **kwargs)

    def build(self, fixture, *, decisions=None, releases=None, reset=None, review=None,
              depth=None):
        selected_depth = depth or fixture.depth
        return build_motion_policy_decision(
            fixture.foot,
            selected_depth,
            review=review or approved_review(),
            decisions=(
                fixture.accept_all(depth=selected_depth)
                if decisions is None else decisions
            ),
            root_release_keys=[] if releases is None else releases,
            draw_order_loop_reset=(
                {"mode": "explicit", "approved": False}
                if reset is None else reset
            ),
        )

    def test_deterministic_ids_source_binding_and_schema(self):
        fixture = self.fixture()
        release = [{
            "tick": 66667,
            "correction_xy_px": [0.0, 0.0],
            "incoming_interpolation": "linear",
            "reason_code": "return-to-authored-root",
        }]
        first = self.build(fixture, releases=release)
        second = self.build(fixture, releases=deepcopy(release))
        self.assertEqual(first.canonical_bytes, second.canonical_bytes)
        self.assertEqual(first.sha256, second.sha256)
        document = first.document
        inventory = fixture.inventory()
        self.assertEqual(
            [row.candidate_id for row in inventory.candidates],
            [row["candidate_id"] for row in document["decisions"]],
        )
        self.assertEqual(inventory.foot_sha256,
                         document["source"]["foot_lock_candidates_sha256"])
        self.assertEqual(inventory.depth_sha256,
                         document["source"]["depth_order_candidates_sha256"])
        self.assertTrue(all(
            set(row) == {"candidate_id", "action", "reason_code", "payload"}
            for row in document["decisions"]
        ))
        require_motion_policy_decision(
            document,
            foot_candidates=fixture.foot,
            depth_candidates=fixture.depth,
        )
        self._schema(document)
        changed = first.document
        changed["review"]["revision"] = 2
        self.assertNotEqual(changed, first.document)

    def test_stale_candidate_sha_and_mismatched_upstream_chain_fail(self):
        fixture = self.fixture()
        document = self.build(fixture).document
        for field in (
            "foot_lock_candidates_sha256", "depth_order_candidates_sha256",
        ):
            changed = deepcopy(document)
            changed["source"][field] = "0" * 64
            with self.subTest(field=field), self.assertRaisesRegex(
                MotionPolicyDecisionValidationError, "stale"
            ):
                require_motion_policy_decision(
                    changed,
                    foot_candidates=fixture.foot,
                    depth_candidates=fixture.depth,
                )
        mismatched = deepcopy(fixture.depth)
        mismatched["source"]["p3"]["rig_sha256"] = "f" * 64
        with self.assertRaisesRegex(
            MotionPolicyCandidateInventoryError, "source chains differ"
        ):
            derive_motion_policy_candidates(fixture.foot, mismatched)

    def test_decisions_must_be_sorted_unique_and_exhaustive(self):
        fixture = self.fixture()
        baseline = self.build(fixture).document
        variants = []
        missing = deepcopy(baseline)
        missing["decisions"].pop()
        variants.append(missing)
        extra = deepcopy(baseline)
        duplicate = deepcopy(extra["decisions"][0])
        duplicate["candidate_id"] = "foot-" + "f" * 64
        extra["decisions"].append(duplicate)
        extra["decisions"].sort(key=lambda row: row["candidate_id"])
        variants.append(extra)
        repeated = deepcopy(baseline)
        repeated["decisions"][1] = deepcopy(repeated["decisions"][0])
        variants.append(repeated)
        reordered = deepcopy(baseline)
        reordered["decisions"].reverse()
        variants.append(reordered)
        for changed in variants:
            with self.assertRaises(MotionPolicyDecisionValidationError):
                require_motion_policy_decision(
                    changed,
                    foot_candidates=fixture.foot,
                    depth_candidates=fixture.depth,
                )

    def test_action_payloads_are_kind_specific(self):
        fixture = self.fixture()
        inventory = fixture.inventory()
        decisions = fixture.accept_all()
        by_id = {row["candidate_id"]: row for row in decisions}
        foot = next(row for row in inventory.candidates if row.kind == "foot_lock")
        depth = next(row for row in inventory.candidates if row.kind == "depth_order")
        by_id[foot.candidate_id].update({
            "action": "adjust",
            "payload": {"final_correction_xy_px": [3.0, -2.0]},
        })
        by_id[depth.candidate_id].update({
            "action": "adjust",
            "payload": {"final_front_slot": depth.depth_slots[1]},
        })
        valid = sorted(by_id.values(), key=lambda row: row["candidate_id"])
        self.build(fixture, decisions=valid)

        invalid = deepcopy(valid)
        row = next(item for item in invalid if item["candidate_id"] == depth.candidate_id)
        row["payload"] = {"final_front_slot": "outside-pair"}
        with self.assertRaisesRegex(MotionPolicyDecisionError, "outside its pair"):
            self.build(fixture, decisions=invalid)
        invalid = deepcopy(valid)
        row = next(item for item in invalid if item["candidate_id"] == foot.candidate_id)
        row["action"] = "reject"
        with self.assertRaisesRegex(MotionPolicyDecisionError, "must be null"):
            self.build(fixture, decisions=invalid)

    def test_automatically_rejected_foot_sample_cannot_be_accepted(self):
        fixture = self.fixture(correction_limit=1e-6)
        rejected = [
            row for row in fixture.inventory().candidates
            if row.kind == "foot_lock" and row.foot_state == "rejected_limit"
        ]
        self.assertTrue(rejected)
        with self.assertRaisesRegex(MotionPolicyDecisionError, "cannot be accepted"):
            self.build(fixture)
        decisions = fixture.accept_all()
        rejected_ids = {row.candidate_id for row in rejected}
        for row in decisions:
            if row["candidate_id"] in rejected_ids:
                row.update({"action": "reject", "reason_code": "over-limit"})
        self.build(fixture, decisions=decisions)

    def test_release_keys_only_use_unconstrained_ticks_and_are_explicit(self):
        fixture = self.fixture()
        valid = [{
            "tick": 66667,
            "correction_xy_px": [1.0, 2.0],
            "incoming_interpolation": "stepped",
            "reason_code": "reviewed-release",
        }]
        self.build(fixture, releases=valid)
        for changed in (
            [{**valid[0], "tick": 0}],
            [valid[0], deepcopy(valid[0])],
            [{**valid[0], "incoming_interpolation": "bezier"}],
        ):
            with self.assertRaises(MotionPolicyDecisionError):
                self.build(fixture, releases=changed)

    def test_review_and_loop_reset_require_explicit_human_authority(self):
        fixture = self.fixture()
        for review in (
            {"status": "draft", "method": "human", "revision": 1},
            {"status": "approved", "method": "automatic", "revision": 1},
            {"status": "approved", "method": "human", "revision": 0},
        ):
            with self.assertRaises(MotionPolicyDecisionError):
                self.build(fixture, review=review)
        with self.assertRaisesRegex(MotionPolicyDecisionError, "requires a loop"):
            self.build(
                fixture,
                reset={"mode": "explicit", "approved": True},
            )
        loop_depth = deepcopy(fixture.depth)
        loop_depth["timing"]["loop"] = True
        self.build(
            fixture,
            depth=loop_depth,
            reset={"mode": "explicit", "approved": True},
        )

    def _schema(self, document: dict) -> None:
        if Draft202012Validator is None:
            self.skipTest("jsonschema optional test dependency is unavailable")
        schema = json.loads((
            ROOT / "schemas" / "motion-policy-decision-v1.schema.json"
        ).read_text("utf-8"))
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(document)


if __name__ == "__main__":
    unittest.main()
