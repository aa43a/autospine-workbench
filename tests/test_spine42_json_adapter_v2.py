"""Policy-aware Spine 4.2 adapter v2 contract and timeline tests."""

from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.resolved_project import canonical_sha256  # noqa: E402
from autospine_workbench.motion_instance_v2_compiler import (  # noqa: E402
    compile_motion_instance_v2,
)
from autospine_workbench.motion_policy_decision import (  # noqa: E402
    build_motion_policy_decision,
)
from autospine_workbench.reviewed_motion_policy import (  # noqa: E402
    compile_reviewed_motion_policy,
)
from autospine_workbench.reviewed_motion_policy_validation import (  # noqa: E402
    reviewed_motion_policy_sha256,
)
from autospine_workbench.spine42_contract import (  # noqa: E402
    SPINE_RUNTIME_VERSION,
    spine42_json_sha256,
)
from autospine_workbench.spine42_contract_v2 import (  # noqa: E402
    Spine42ContractV2Error,
    spine42_target_profile_v2,
)
from autospine_workbench.spine42_draw_order_offsets import (  # noqa: E402
    apply_spine42_draw_order_offsets,
)
from autospine_workbench.spine42_json_adapter import (  # noqa: E402
    build_spine42_json,
)
from autospine_workbench.spine42_json_adapter_v2 import (  # noqa: E402
    build_spine42_json_bytes_v2,
    build_spine42_json_v2,
)
from tests.test_spine42_json_adapter import (  # noqa: E402
    motion_pair,
    rig_fixture,
)
from tests.motion_policy_decision_helpers import (  # noqa: E402
    MotionPolicyDecisionFixture,
    approved_review,
)


def instance_v2_fixture(rig: dict, target: dict, base: dict) -> dict:
    setup = [
        item["id"]
        for item in sorted(
            rig["slots"],
            key=lambda row: (row["setup_draw_order"], row["id"]),
        )
    ]
    value = deepcopy(base)
    value["format_version"] = 2
    value["source"] = {
        "base_motion_instance_sha256": canonical_sha256(base),
        "base_retarget_bundle_sha256": "6" * 64,
        "target_profile_sha256": canonical_sha256(target),
        "reviewed_motion_policy_sha256": "7" * 64,
        "motion_policy_decision_sha256": "8" * 64,
        "p3_rig_sha256": canonical_sha256(rig),
        "p3_bundle_sha256": target["source"]["p3"]["bundle_sha256"],
    }
    value["target_space"] = {
        **base["target_space"],
        "draw_order": "full-back-to-front-stepped",
    }
    value["draw_order"] = {
        "setup_slot_ids": setup,
        "keys": [
            {"tick": 0, "slot_ids": setup},
            {"tick": 250_000, "slot_ids": list(reversed(setup))},
            {"tick": 1_000_000, "slot_ids": setup},
        ],
    }
    return value


class Spine42JsonAdapterV2Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.rig = rig_fixture()
        self.target, self.base = motion_pair(self.rig)
        self.instance = instance_v2_fixture(self.rig, self.target, self.base)

    def build(self) -> dict:
        return build_spine42_json_v2(
            self.rig,
            motion_instance=self.instance,
            target_profile=self.target,
        )

    def test_profile_is_isolated_and_exactly_version_locked(self) -> None:
        profile = spine42_target_profile_v2()
        self.assertEqual("2.0.0", profile["adapter"]["version"])
        self.assertEqual("4.2", profile["spine_major_minor"])
        self.assertEqual(SPINE_RUNTIME_VERSION, profile["runtime"]["version"])

    def test_bone_marker_and_policy_timelines_preserve_v1_projection(self) -> None:
        result = self.build()
        animation = result["animations"]["wave.left"]
        self.assertEqual(
            20.0,
            animation["bones"]["forearm.left"]["rotate"][1]["value"],
        )
        root = animation["bones"]["root-pelvis"]["translate"][1]
        self.assertEqual((1.5, 2.0), (root["x"], root["y"]))
        self.assertEqual(4, len(animation["events"]))
        self.assertIn("drawOrder", animation)
        self.assertNotIn("draw_order", animation)

        setup = tuple(self.instance["draw_order"]["setup_slot_ids"])
        frames = animation["drawOrder"]
        self.assertEqual([0.0, 0.25, 1.0], [row["time"] for row in frames])
        self.assertEqual({"time": 0.0}, frames[0])
        self.assertEqual({"time": 1.0}, frames[-1])
        targets = [
            tuple(key["slot_ids"])
            for key in self.instance["draw_order"]["keys"]
        ]
        for frame, target in zip(frames, targets):
            self.assertEqual(
                target,
                apply_spine42_draw_order_offsets(
                    setup, frame.get("offsets", [])
                ),
            )

    def test_skeleton_hash_binds_the_complete_v2_adapter_source(self) -> None:
        result = self.build()
        expected = canonical_sha256({
            "adapter_profile": spine42_target_profile_v2(),
            "rig_sha256": canonical_sha256(self.rig),
            "motion_instance_v2_sha256": canonical_sha256(self.instance),
            "target_profile_sha256": canonical_sha256(self.target),
        })
        self.assertEqual(expected, result["skeleton"]["hash"])
        self.assertEqual(
            build_spine42_json_bytes_v2(
                self.rig,
                motion_instance=self.instance,
                target_profile=self.target,
            ),
            build_spine42_json_bytes_v2(
                deepcopy(self.rig),
                motion_instance=deepcopy(self.instance),
                target_profile=deepcopy(self.target),
            ),
        )
        self.assertEqual(
            "8ea1bbfba60bc5ae9489176b4d6fd45ace71617a9ad5ce9f1cb27e7769408064",
            hashlib.sha256(build_spine42_json_bytes_v2(
                self.rig,
                motion_instance=self.instance,
                target_profile=self.target,
            )).hexdigest(),
        )

    def test_exact_review_chain_compiles_through_the_v2_adapter(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = MotionPolicyDecisionFixture(Path(temporary))
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
            instance = compile_motion_instance_v2(
                fixture.upstream.retarget.motion_instance,
                fixture.upstream.target.document,
                policy,
            ).document
            result = build_spine42_json_v2(
                fixture.upstream.mesh.rig,
                motion_instance=instance,
                target_profile=fixture.upstream.target.document,
            )
        animation = result["animations"][instance["clip_id"]]
        self.assertEqual(
            len(instance["draw_order"]["keys"]),
            len(animation["drawOrder"]),
        )
        self.assertEqual(
            instance["source"]["reviewed_motion_policy_sha256"],
            reviewed_motion_policy_sha256(policy),
        )

    def test_v1_adapter_hash_sentinel_remains_unchanged(self) -> None:
        self.assertEqual(
            "06bbbb1ffa5633890b1a95d09a2f24a25611e03e78b7ffafeba6b65aac657d6b",
            spine42_json_sha256(build_spine42_json(self.rig)),
        )
        self.assertEqual(
            "7d481c8a7ff893343057e69064c3731d8a9cd97efd849fc5846254ce09299dad",
            spine42_json_sha256(build_spine42_json(
                self.rig,
                motion_instance=self.base,
                target_profile=self.target,
            )),
        )

    def test_stale_or_unrepresentable_p3_and_instance_fail_closed(self) -> None:
        stale = deepcopy(self.instance)
        stale["source"]["p3_rig_sha256"] = "f" * 64
        with self.assertRaises(Spine42ContractV2Error):
            build_spine42_json_v2(
                self.rig, motion_instance=stale, target_profile=self.target
            )

        wrong_slots = deepcopy(self.instance)
        wrong_slots["draw_order"]["setup_slot_ids"] = ["other", "face"]
        for key in wrong_slots["draw_order"]["keys"]:
            key["slot_ids"] = (
                ["other", "face"]
                if key["tick"] != 250_000 else ["face", "other"]
            )
        with self.assertRaisesRegex(Spine42ContractV2Error, "setup slots"):
            build_spine42_json_v2(
                self.rig,
                motion_instance=wrong_slots,
                target_profile=self.target,
            )

        invalid = deepcopy(self.instance)
        invalid["draw_order"]["keys"][0]["tick"] = 1
        with self.assertRaises(Spine42ContractV2Error):
            build_spine42_json_v2(
                self.rig,
                motion_instance=invalid,
                target_profile=self.target,
            )

        unsafe_rig = deepcopy(self.rig)
        unsafe_rig["bones"][0]["setup"]["scale_x"] = 2.0
        with self.assertRaises(Spine42ContractV2Error):
            build_spine42_json_v2(
                unsafe_rig,
                motion_instance=self.instance,
                target_profile=self.target,
            )


if __name__ == "__main__":
    unittest.main()
