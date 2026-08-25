"""Resolution tests for reviewer-authored bilateral split specifications."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.split_spec_resolution import (  # noqa: E402
    SplitSpecResolutionError,
    resolve_split_spec,
)


def joint(joint_id: str) -> dict[str, str]:
    return {"kind": "joint", "joint_id": joint_id}


def proxy(side: str, xy: list[float]) -> dict:
    return {
        "kind": "manual_proxy",
        "proxy_id": f"shoe-opening.{side}",
        "xy": xy,
        "label": "shoe opening",
        "reason": "the anatomical ankle is hidden by the costume",
        "proxy_for_joint_id": f"ankle.{side}",
    }


def spec_fixture() -> dict:
    return {
        "parts": {
            "left": {
                "guide": [joint("knee.left"), proxy("left", [25, 90])],
                "pivot": proxy("left", [25, 90]),
                "candidate_bone": "calf.left",
            },
            "right": {
                "guide": [joint("knee.right"), joint("ankle.right")],
                "pivot": joint("ankle.right"),
                "candidate_bone": "calf.right",
            },
        }
    }


def joints_fixture() -> dict[str, dict]:
    return {
        "knee.left": {
            "id": "knee.left",
            "x": 30,
            "y": 60,
            "review_state": "candidate_accepted",
        },
        "ankle.left": {
            "id": "ankle.left",
            "x": 30,
            "y": 90,
            "review_state": "unobservable",
        },
        "knee.right": {
            "id": "knee.right",
            "x": 70,
            "y": 60,
            "review_state": "manual_adjusted",
        },
        "ankle.right": {
            "id": "ankle.right",
            "x": 70,
            "y": 90,
            "review_state": "manual_adjusted",
        },
    }


class SplitSpecResolutionTests(unittest.TestCase):
    def resolve(self, spec: dict | None = None, joints: dict | None = None) -> dict:
        return resolve_split_spec(
            "layer-footwear",
            spec or spec_fixture(),
            joints=joints or joints_fixture(),
            bone_ids={"calf.left", "calf.right"},
            canvas_width=100,
            canvas_height=100,
        )

    def test_resolves_reviewed_joints_and_preserves_manual_proxy_provenance(self) -> None:
        spec = spec_fixture()
        joints = joints_fixture()
        before = (deepcopy(spec), deepcopy(joints))

        first = self.resolve(spec, joints)
        second = self.resolve(spec, joints)

        self.assertEqual(first, second)
        self.assertEqual(before, (spec, joints))
        self.assertEqual(64, len(first["split_spec_sha256"]))
        left = first["parts"]["left"]
        right = first["parts"]["right"]
        self.assertEqual("resolved_joint", left["guide_anchors"][0]["kind"])
        self.assertEqual("candidate_accepted", left["guide_anchors"][0]["review_state"])
        self.assertEqual(proxy("left", [25, 90]), left["guide_anchors"][1])
        self.assertEqual([25.0, 90.0], left["pivot_xy"])
        self.assertEqual([70.0, 90.0], right["pivot_xy"])
        self.assertEqual("calf.right", right["candidate_bone"])

    def test_hash_changes_when_authored_proxy_provenance_changes(self) -> None:
        first = self.resolve()
        changed = spec_fixture()
        changed["parts"]["left"]["guide"][1]["reason"] = "different reviewed landmark"
        second = self.resolve(changed)
        self.assertNotEqual(first["split_spec_sha256"], second["split_spec_sha256"])

    def test_unaccepted_joint_requires_an_explicit_manual_proxy(self) -> None:
        spec = spec_fixture()
        spec["parts"]["left"]["guide"][1] = joint("ankle.left")
        with self.assertRaisesRegex(SplitSpecResolutionError, "manual_proxy"):
            self.resolve(spec)

    def test_invalid_effective_joint_coordinates_fail_closed(self) -> None:
        for value in ((float("nan"), 90), (101, 90)):
            with self.subTest(value=value):
                joints = joints_fixture()
                joints["ankle.right"].update(x=value[0], y=value[1])
                with self.assertRaises(SplitSpecResolutionError):
                    self.resolve(joints=joints)

    def test_distinct_authored_joints_may_not_resolve_to_duplicate_points(self) -> None:
        joints = joints_fixture()
        joints["ankle.right"].update(x=70, y=60)
        with self.assertRaisesRegex(SplitSpecResolutionError, "duplicate points"):
            self.resolve(joints=joints)

    def test_unknown_bones_and_malformed_specs_fail_closed(self) -> None:
        with self.assertRaisesRegex(SplitSpecResolutionError, "unknown bone"):
            resolve_split_spec(
                "layer-footwear",
                spec_fixture(),
                joints=joints_fixture(),
                bone_ids={"calf.left"},
                canvas_width=100,
                canvas_height=100,
            )
        malformed = spec_fixture()
        malformed["parts"]["left"]["unexpected"] = True
        with self.assertRaisesRegex(SplitSpecResolutionError, "unknown field"):
            self.resolve(malformed)


if __name__ == "__main__":
    unittest.main()
