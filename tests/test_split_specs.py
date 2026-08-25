from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.contracts import (  # noqa: E402
    ContractValidationError,
    normalize_override_request,
)
from autospine_workbench.split_specs import (  # noqa: E402
    infer_humanoid_bone_ids,
    normalize_split_spec,
)

JOINTS = {
    "root",
    "pelvis",
    "spine",
    "chest",
    "neck",
    "head",
    *{
        f"{name}.{side}"
        for name in ("shoulder", "elbow", "wrist", "hip", "knee", "ankle")
        for side in ("left", "right")
    },
}
BONES = infer_humanoid_bone_ids(JOINTS)


def joint(joint_id: str) -> dict[str, str]:
    return {"kind": "joint", "joint_id": joint_id}


def proxy(
    x: float,
    y: float,
    *,
    proxy_id: str = "shoe-opening.left",
    label: str = "shoe opening",
) -> dict:
    return {
        "kind": "manual_proxy",
        "proxy_id": proxy_id,
        "xy": [x, y],
        "label": label,
        "reason": "the anatomical ankle is hidden by the costume",
    }


def valid_spec() -> dict:
    return {
        "parts": {
            "left": {
                "guide": [joint("hip.left"), joint("knee.left"), proxy(70, 160)],
                "pivot": joint("hip.left"),
                "candidate_bone": "thigh.left",
            },
            "right": {
                "guide": [
                    joint("hip.right"),
                    joint("knee.right"),
                    proxy(30, 160, proxy_id="shoe-opening.right"),
                ],
                "pivot": joint("hip.right"),
                "candidate_bone": "thigh.right",
            },
        }
    }


def valid_patch(*, version: str | None = "autospine-workbench.override/v3") -> dict:
    patch = {
        "base_revision": 2,
        "joint_overrides": {},
        "joint_decisions": {},
        "layer_overrides": {
            "layer-footwear": {
                "canonical_role": "body.foot",
                "side": "bilateral",
                "disposition": "split",
                "split_spec": valid_spec(),
                "visible": True,
            }
        },
        "notes": "reviewed split anchors",
    }
    if version is not None:
        patch["schema_version"] = version
    return patch


def normalize_patch(patch: dict) -> dict:
    _, normalized = normalize_override_request(
        patch,
        project_id="sample",
        current_revision=2,
        joint_ids=JOINTS,
        bone_ids=BONES,
        layer_ids={"layer-footwear"},
        canvas_width=100,
        canvas_height=200,
    )
    return normalized


class SplitSpecNormalizationTests(unittest.TestCase):
    def test_strict_spec_normalizes_points_without_mutating_input(self) -> None:
        source = valid_spec()
        before = copy.deepcopy(source)
        issues = []
        normalized = normalize_split_spec(
            source,
            path="$.split_spec",
            joint_ids=JOINTS,
            bone_ids=BONES,
            canvas_width=100,
            canvas_height=200,
            issues=issues,
        )

        self.assertEqual([], issues)
        self.assertEqual(source, before)
        self.assertEqual([70.0, 160.0], normalized["parts"]["left"]["guide"][2]["xy"])

    def test_contract_canonicalizes_split_alias_and_writes_v3(self) -> None:
        normalized = normalize_patch(valid_patch())
        layer = normalized["layer_overrides"]["layer-footwear"]

        self.assertEqual("autospine-workbench.override/v3", normalized["schema_version"])
        self.assertEqual(
            {"name": "autospine-workbench.override", "version": 3},
            normalized["contract"],
        )
        self.assertEqual("split_left_right", layer["disposition"])
        self.assertEqual(valid_spec()["parts"].keys(), layer["split_spec"]["parts"].keys())

    def test_explicit_v1_and_v2_documents_migrate_but_cannot_claim_v3_fields(self) -> None:
        for version in (
            "autospine-workbench.override/v1",
            "autospine-workbench.override/v2",
        ):
            with self.subTest(version=version):
                legacy = valid_patch(version=version)
                legacy["layer_overrides"] = {}
                self.assertEqual(
                    "autospine-workbench.override/v3",
                    normalize_patch(legacy)["schema_version"],
                )

                with self.assertRaises(ContractValidationError) as caught:
                    normalize_patch(valid_patch(version=version))
                self.assertIn("version", {issue.code for issue in caught.exception.issues})

    def test_parent_rig_fields_and_non_bilateral_split_are_conflicts(self) -> None:
        patch = valid_patch()
        layer = patch["layer_overrides"]["layer-footwear"]
        layer.update(side="left", disposition="keep", pivot_xy=[1, 2], candidate_bone="calf.left")

        with self.assertRaises(ContractValidationError) as caught:
            normalize_patch(patch)
        conflicts = [issue.path for issue in caught.exception.issues if issue.code == "conflict"]
        self.assertTrue(any(path.endswith(".side") for path in conflicts))
        self.assertTrue(any(path.endswith(".disposition") for path in conflicts))
        self.assertTrue(any(path.endswith(".pivot_xy") for path in conflicts))
        self.assertTrue(any(path.endswith(".candidate_bone") for path in conflicts))

    def test_unknown_and_opposite_side_joint_or_bone_ids_are_rejected(self) -> None:
        spec = valid_spec()
        left = spec["parts"]["left"]
        left["guide"][0] = joint("hip.right")
        left["pivot"] = joint("missing.left")
        left["candidate_bone"] = "thigh.right"
        issues = []

        self.assertIsNone(
            normalize_split_spec(
                spec,
                path="$.split_spec",
                joint_ids=JOINTS,
                bone_ids=BONES,
                canvas_width=100,
                canvas_height=200,
                issues=issues,
            )
        )
        self.assertTrue({"unknown_id", "side_mismatch"}.issubset({item.code for item in issues}))

    def test_manual_proxies_require_bounded_points_and_nonblank_provenance(self) -> None:
        spec = valid_spec()
        bad = spec["parts"]["left"]["guide"][2]
        bad.update(xy=[101, 160], label=" ", reason="")
        issues = []

        normalize_split_spec(
            spec,
            path="$.split_spec",
            joint_ids=JOINTS,
            bone_ids=BONES,
            canvas_width=100,
            canvas_height=200,
            issues=issues,
        )
        self.assertTrue({"bounds", "length"}.issubset({item.code for item in issues}))

    def test_manual_proxy_requires_stable_side_specific_identity(self) -> None:
        for proxy_id, expected_code in (
            (None, "required"),
            ("../shoe.left", "format"),
            ("shoe-opening.right", "side_mismatch"),
        ):
            with self.subTest(proxy_id=proxy_id):
                spec = valid_spec()
                anchor = spec["parts"]["left"]["guide"][2]
                if proxy_id is None:
                    del anchor["proxy_id"]
                else:
                    anchor["proxy_id"] = proxy_id
                issues = []
                self.assertIsNone(
                    normalize_split_spec(
                        spec,
                        path="$.split_spec",
                        joint_ids=JOINTS,
                        bone_ids=BONES,
                        canvas_width=100,
                        canvas_height=200,
                        issues=issues,
                    )
                )
                self.assertIn(expected_code, {item.code for item in issues})

    def test_manual_proxy_may_name_the_hidden_joint_it_substitutes(self) -> None:
        spec = valid_spec()
        proxy_anchor = spec["parts"]["left"]["guide"][2]
        proxy_anchor["proxy_for_joint_id"] = "ankle.left"
        issues = []

        normalized = normalize_split_spec(
            spec,
            path="$.split_spec",
            joint_ids=JOINTS,
            bone_ids=BONES,
            canvas_width=100,
            canvas_height=200,
            issues=issues,
        )
        self.assertEqual([], issues)
        self.assertEqual(
            "ankle.left",
            normalized["parts"]["left"]["guide"][2]["proxy_for_joint_id"],
        )

        proxy_anchor["proxy_for_joint_id"] = "ankle.right"
        issues = []
        self.assertIsNone(
            normalize_split_spec(
                spec,
                path="$.split_spec",
                joint_ids=JOINTS,
                bone_ids=BONES,
                canvas_width=100,
                canvas_height=200,
                issues=issues,
            )
        )
        self.assertIn("side_mismatch", {item.code for item in issues})

    def test_duplicate_and_repeated_guide_anchors_are_rejected(self) -> None:
        duplicate = valid_spec()
        duplicate["parts"]["left"]["guide"] = [
            joint("hip.left"),
            joint("knee.left"),
            joint("hip.left"),
        ]
        repeated = valid_spec()
        repeated["parts"]["left"]["guide"][1:] = [
            proxy(70, 160, proxy_id="first.left"),
            proxy(70, 160, proxy_id="second.left"),
        ]

        for spec, expected in ((duplicate, "duplicate_id"), (repeated, "degenerate")):
            with self.subTest(expected=expected):
                issues = []
                self.assertIsNone(
                    normalize_split_spec(
                        spec,
                        path="$.split_spec",
                        joint_ids=JOINTS,
                        bone_ids=BONES,
                        canvas_width=100,
                        canvas_height=200,
                        issues=issues,
                    )
                )
                self.assertIn(expected, {item.code for item in issues})

    def test_identical_or_reversed_authored_guides_are_rejected(self) -> None:
        for right_guide in (
            [joint("root"), joint("pelvis")],
            [joint("pelvis"), joint("root")],
        ):
            with self.subTest(right_guide=right_guide):
                spec = valid_spec()
                spec["parts"]["left"]["guide"] = [joint("root"), joint("pelvis")]
                spec["parts"]["right"]["guide"] = right_guide
                issues = []
                self.assertIsNone(
                    normalize_split_spec(
                        spec,
                        path="$.split_spec",
                        joint_ids=JOINTS,
                        bone_ids=BONES,
                        canvas_width=100,
                        canvas_height=200,
                        issues=issues,
                    )
                )
                self.assertIn("degenerate", {item.code for item in issues})

    def test_split_candidate_bone_must_have_the_part_side_suffix(self) -> None:
        spec = valid_spec()
        spec["parts"]["left"]["candidate_bone"] = "pelvis-spine"
        issues = []
        self.assertIsNone(
            normalize_split_spec(
                spec,
                path="$.split_spec",
                joint_ids=JOINTS,
                bone_ids=BONES,
                canvas_width=100,
                canvas_height=200,
                issues=issues,
            )
        )
        self.assertIn("side_mismatch", {item.code for item in issues})

    def test_parts_guides_and_anchors_are_closed_shapes(self) -> None:
        spec = valid_spec()
        spec["parts"]["extra"] = spec["parts"]["left"]
        spec["parts"]["right"]["guide"] = [joint("hip.right")]
        spec["parts"]["left"]["pivot"]["extra"] = True
        issues = []

        normalize_split_spec(
            spec,
            path="$.split_spec",
            joint_ids=JOINTS,
            bone_ids=BONES,
            canvas_width=100,
            canvas_height=200,
            issues=issues,
        )
        self.assertTrue({"unknown_field", "length"}.issubset({item.code for item in issues}))

if __name__ == "__main__":
    unittest.main()
