"""MotionInstance v2 reviewed-policy overlay compiler tests."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.motion_instance_v2_compiler import (  # noqa: E402
    MotionInstanceV2CompilerError,
    compile_motion_instance_v2,
)
from autospine_workbench.motion_instance_v2_validation import (  # noqa: E402
    require_motion_instance_v2,
)
from autospine_workbench.motion_policy_decision import (  # noqa: E402
    build_motion_policy_decision,
)
from autospine_workbench.resolved_project import canonical_sha256  # noqa: E402
from autospine_workbench.reviewed_motion_policy import (  # noqa: E402
    compile_reviewed_motion_policy,
)
from tests.motion_policy_decision_helpers import (  # noqa: E402
    MotionPolicyDecisionFixture,
    approved_review,
)


ROOT_TRACK = ("root-pelvis", "translation")


class MotionInstanceV2CompilerTests(unittest.TestCase):
    def fixture(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        fixture = MotionPolicyDecisionFixture(Path(temporary.name))
        decision = build_motion_policy_decision(
            fixture.foot,
            fixture.depth,
            review=approved_review(),
            decisions=fixture.accept_all(),
            root_release_keys=[],
            draw_order_loop_reset={"mode": "explicit", "approved": False},
        ).document
        policy = compile_reviewed_motion_policy(
            decision, fixture.foot, fixture.depth, fixture.upstream.mesh
        ).document
        return (
            fixture.upstream.retarget.motion_instance,
            fixture.upstream.target.document,
            policy,
        )

    def test_compiles_canonical_overlay_and_preserves_inputs(self):
        base, target, policy = self.fixture()
        before = deepcopy((base, target, policy))
        first = compile_motion_instance_v2(base, target, policy)
        second = compile_motion_instance_v2(
            deepcopy(base), deepcopy(target), deepcopy(policy)
        )
        self.assertEqual(first.canonical_bytes, second.canonical_bytes)
        self.assertEqual(first.sha256, second.sha256)
        self.assertEqual(before, (base, target, policy))
        document = first.document
        require_motion_instance_v2(
            document,
            target_profile=target,
            base_motion_instance=base,
            reviewed_motion_policy=policy,
        )
        self.assertEqual(policy["slot_order"], document["draw_order"])
        self.assertEqual(base["markers"], document["markers"])
        changed = first.document
        changed["markers"].append({"not": "stored"})
        self.assertNotEqual(changed, first.document)

    def test_union_schedule_linearly_samples_both_sources(self):
        base, target, policy = self.fixture()
        root = self._root_track(base)
        root["keys"] = [
            {"tick": 0, "value": [0.0, 0.0]},
            {"tick": 10_000, "value": [10.0, 2.0]},
            {"tick": 66_667, "value": [20.0, 0.0]},
        ]
        self._bind_base(policy, base)
        document = compile_motion_instance_v2(base, target, policy).document
        keys = self._root_track(document)["keys"]
        self.assertEqual([0, 10_000, 33_333, 66_667], [row["tick"] for row in keys])

        correction = policy["root_correction_keys"][1]["correction_xy_px"]
        at_ten_ratio = 10_000 / 33_333
        self.assertAlmostEqual(
            10.0 + correction[0] * at_ten_ratio,
            keys[1]["value"][0], places=8,
        )
        self.assertAlmostEqual(
            2.0 + correction[1] * at_ten_ratio,
            keys[1]["value"][1], places=8,
        )
        base_ratio = (33_333 - 10_000) / (66_667 - 10_000)
        self.assertAlmostEqual(
            10.0 + 10.0 * base_ratio + correction[0],
            keys[2]["value"][0], places=8,
        )

    def test_missing_base_root_creates_full_correction_track(self):
        base, target, policy = self.fixture()
        base["tracks"] = [
            row for row in base["tracks"]
            if (row["bone_id"], row["property"]) != ROOT_TRACK
        ]
        original_other_tracks = deepcopy(base["tracks"])
        self._bind_base(policy, base)
        document = compile_motion_instance_v2(base, target, policy).document
        root = self._root_track(document)
        self.assertEqual(
            [row["tick"] for row in policy["root_correction_keys"]],
            [row["tick"] for row in root["keys"]],
        )
        self.assertEqual(
            [row["correction_xy_px"] for row in policy["root_correction_keys"]],
            [row["value"] for row in root["keys"]],
        )
        self.assertEqual(
            original_other_tracks,
            [row for row in document["tracks"]
             if (row["bone_id"], row["property"]) != ROOT_TRACK],
        )

    def test_loop_overlay_preserves_equal_endpoints(self):
        base, target, policy = self.fixture()
        base["timing"]["loop"] = True
        for track in base["tracks"]:
            track["keys"][-1]["value"] = deepcopy(track["keys"][0]["value"])
        policy["timing"]["loop"] = True
        policy["slot_order"]["keys"] = [{
            "tick": 0,
            "slot_ids": deepcopy(policy["slot_order"]["setup_slot_ids"]),
        }]
        self._bind_base(policy, base)
        document = compile_motion_instance_v2(base, target, policy).document
        root = self._root_track(document)["keys"]
        self.assertEqual(root[0]["value"], root[-1]["value"])
        self.assertTrue(document["timing"]["loop"])
        self.assertEqual(1, len(document["draw_order"]["keys"]))

    def test_stale_base_target_or_p3_binding_fails_closed(self):
        base, target, policy = self.fixture()
        stale_base = deepcopy(policy)
        stale_base["source"]["p5"]["instance_sha256"] = "f" * 64
        with self.assertRaises(MotionInstanceV2CompilerError):
            compile_motion_instance_v2(base, target, stale_base)
        stale_target = deepcopy(policy)
        stale_target["source"]["p5"]["target_profile_sha256"] = "e" * 64
        with self.assertRaises(MotionInstanceV2CompilerError):
            compile_motion_instance_v2(base, target, stale_target)
        stale_p3 = deepcopy(policy)
        stale_p3["source"]["p3"]["rig_sha256"] = "d" * 64
        with self.assertRaises(MotionInstanceV2CompilerError):
            compile_motion_instance_v2(base, target, stale_p3)
        wrong_project = deepcopy(policy)
        wrong_project["project_id"] = "different-project"
        with self.assertRaisesRegex(MotionInstanceV2CompilerError, "projects"):
            compile_motion_instance_v2(base, target, wrong_project)

    @staticmethod
    def _root_track(document):
        return next(
            row for row in document["tracks"]
            if (row["bone_id"], row["property"]) == ROOT_TRACK
        )

    @staticmethod
    def _bind_base(policy, base):
        policy["source"]["p5"]["instance_sha256"] = canonical_sha256(base)


if __name__ == "__main__":
    unittest.main()
