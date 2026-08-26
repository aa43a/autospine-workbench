"""Deterministic runtime-semantic replay tests for Spine adapter v2."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import math
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.motion_instance_v2_compiler import (  # noqa: E402
    compile_motion_instance_v2,
)
from autospine_workbench.motion_policy_decision import (  # noqa: E402
    build_motion_policy_decision,
)
from autospine_workbench.resolved_project import canonical_sha256  # noqa: E402
from autospine_workbench.reviewed_motion_policy import (  # noqa: E402
    compile_reviewed_motion_policy,
)
from autospine_workbench.spine42_json_adapter_v2 import (  # noqa: E402
    build_spine42_json_v2,
)
from autospine_workbench.spine42_v2_runtime_semantics import (  # noqa: E402
    FORMAT,
    Spine42V2RuntimeSemanticsError,
    audit_spine42_v2_runtime_semantics,
)
from tests.motion_policy_decision_helpers import (  # noqa: E402
    MotionPolicyDecisionFixture,
    approved_review,
)


class Spine42V2RuntimeSemanticsTests(unittest.TestCase):
    def chain(self, *, reject_depth=False, loop_dynamic=False):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        fixture = MotionPolicyDecisionFixture(Path(temporary.name))
        decisions = fixture.accept_all()
        if reject_depth:
            for row in decisions:
                if row["candidate_id"].startswith("depth-"):
                    row.update({
                        "action": "reject",
                        "reason_code": "keep-reviewed-setup-order",
                    })
        decision = build_motion_policy_decision(
            fixture.foot,
            fixture.depth,
            review=approved_review(),
            decisions=decisions,
            root_release_keys=[],
            draw_order_loop_reset={"mode": "explicit", "approved": False},
        ).document
        policy = compile_reviewed_motion_policy(
            decision, fixture.foot, fixture.depth, fixture.upstream.mesh
        ).document
        base = fixture.upstream.retarget.motion_instance
        if loop_dynamic:
            base = deepcopy(base)
            base["timing"]["loop"] = True
            for track in base["tracks"]:
                track["keys"][-1]["value"] = deepcopy(
                    track["keys"][0]["value"]
                )
            policy["timing"]["loop"] = True
            duration = base["timing"]["duration_ticks"]
            setup = policy["slot_order"]["setup_slot_ids"]
            front = policy["slot_order"]["keys"][-1]["slot_ids"]
            policy["slot_order"]["keys"] = [
                {"tick": 0, "slot_ids": deepcopy(setup)},
                {"tick": duration // 2, "slot_ids": deepcopy(front)},
                {"tick": duration, "slot_ids": deepcopy(setup)},
            ]
            policy["source"]["p5"]["instance_sha256"] = canonical_sha256(base)
        target = fixture.upstream.target.document
        instance = compile_motion_instance_v2(base, target, policy).document
        skeleton = build_spine42_json_v2(
            fixture.upstream.mesh.rig,
            motion_instance=instance,
            target_profile=target,
        )
        return skeleton, instance

    def audit(self, skeleton, instance, ticks):
        return audit_spine42_v2_runtime_semantics(
            skeleton,
            instance["clip_id"],
            ticks,
            timing=instance["timing"],
        )

    def test_exact_chain_replays_crossing_and_reflected_root(self):
        skeleton, instance = self.chain()
        duration = instance["timing"]["duration_ticks"]
        ticks = [0, 33_332, 33_333, duration - 1, duration]
        before = deepcopy(skeleton)
        audit = self.audit(skeleton, instance, ticks)
        report = audit.document
        self.assertEqual(FORMAT, report["format"])
        self.assertFalse(report["semantics"]["raster_truth_claimed"])
        self.assertEqual(before, skeleton)
        self.assertEqual(
            ["leg", "face"], report["samples"][-2]["slot_ids"]
        )
        self.assertEqual(
            ["face", "leg"], report["samples"][-1]["slot_ids"]
        )
        root = next(
            row for row in instance["tracks"]
            if row["bone_id"] == "root-pelvis"
            and row["property"] == "translation"
        )
        source_mid = next(row for row in root["keys"] if row["tick"] == 33_333)
        report_mid = next(row for row in report["samples"] if row["tick"] == 33_333)
        self.assertEqual(source_mid["value"][0], report_mid["root_xy"][0])
        self.assertEqual(-source_mid["value"][1], report_mid["root_xy"][1])
        second = self.audit(deepcopy(skeleton), deepcopy(instance), ticks)
        self.assertEqual(audit.canonical_bytes, second.canonical_bytes)
        self.assertEqual(audit.sha256, second.sha256)

    def test_static_draw_order_remains_setup_at_arbitrary_ticks(self):
        skeleton, instance = self.chain(reject_depth=True)
        duration = instance["timing"]["duration_ticks"]
        report = self.audit(
            skeleton, instance, [0, 1, duration // 2, duration]
        ).document
        setup = report["setup_slot_ids"]
        self.assertTrue(all(row["slot_ids"] == setup for row in report["samples"]))
        self.assertIsNone(report["wrap_sample"])

    def test_loop_has_explicit_duration_reset_and_cycle_one_wrap(self):
        skeleton, instance = self.chain(loop_dynamic=True)
        duration = instance["timing"]["duration_ticks"]
        crossing = duration // 2
        report = self.audit(
            skeleton, instance, [0, crossing - 1, crossing, duration]
        ).document
        samples = report["samples"]
        self.assertEqual(report["setup_slot_ids"], samples[1]["slot_ids"])
        self.assertNotEqual(report["setup_slot_ids"], samples[2]["slot_ids"])
        self.assertEqual(report["setup_slot_ids"], samples[-1]["slot_ids"])
        self.assertEqual(samples[0]["root_xy"], samples[-1]["root_xy"])
        self.assertEqual({
            "cycle": 1,
            "tick": 0,
            "time": 0.0,
            "slot_ids": samples[0]["slot_ids"],
            "root_xy": samples[0]["root_xy"],
        }, report["wrap_sample"])

    def test_rejects_casing_nonfinite_order_slot_offset_and_missing_zero(self):
        skeleton, instance = self.chain()
        duration = instance["timing"]["duration_ticks"]
        animation = skeleton["animations"][instance["clip_id"]]
        cases = []
        snake = deepcopy(skeleton)
        row = snake["animations"][instance["clip_id"]]
        row["draw_order"] = row.pop("drawOrder")
        cases.append(snake)
        nonfinite = deepcopy(skeleton)
        nonfinite["animations"][instance["clip_id"]]["drawOrder"][0]["time"] = math.nan
        cases.append(nonfinite)
        unordered = deepcopy(skeleton)
        unordered["animations"][instance["clip_id"]]["drawOrder"].reverse()
        cases.append(unordered)
        wrong_slot = deepcopy(skeleton)
        changed = wrong_slot["animations"][instance["clip_id"]]["drawOrder"][-1]
        changed["offsets"][0]["slot"] = "missing"
        cases.append(wrong_slot)
        wrong_offset = deepcopy(skeleton)
        changed = wrong_offset["animations"][instance["clip_id"]]["drawOrder"][-1]
        changed["offsets"][0]["offset"] = 99
        cases.append(wrong_offset)
        missing_zero = deepcopy(skeleton)
        missing_zero["animations"][instance["clip_id"]]["drawOrder"].pop(0)
        cases.append(missing_zero)
        self.assertIn("drawOrder", animation)
        for index, invalid in enumerate(cases):
            with self.subTest(index=index), self.assertRaises(
                Spine42V2RuntimeSemanticsError
            ):
                self.audit(invalid, instance, [0, duration])

    def test_rejects_bad_queries_root_schedule_and_loop_reset(self):
        skeleton, instance = self.chain(loop_dynamic=True)
        duration = instance["timing"]["duration_ticks"]
        for ticks in ([1, duration], [0, duration, duration - 1], [0]):
            with self.subTest(ticks=ticks), self.assertRaises(
                Spine42V2RuntimeSemanticsError
            ):
                self.audit(skeleton, instance, ticks)
        bad_root = deepcopy(skeleton)
        root = bad_root["animations"][instance["clip_id"]]["bones"][
            "root-pelvis"
        ]["translate"]
        root.pop(0)
        with self.assertRaises(Spine42V2RuntimeSemanticsError):
            self.audit(bad_root, instance, [0, duration])
        no_reset = deepcopy(skeleton)
        no_reset["animations"][instance["clip_id"]]["drawOrder"].pop()
        with self.assertRaises(Spine42V2RuntimeSemanticsError):
            self.audit(no_reset, instance, [0, duration])


if __name__ == "__main__":
    unittest.main()
