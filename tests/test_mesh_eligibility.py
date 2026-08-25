"""P3 hinge eligibility from reviewed manifests and verified P2 RigIR."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.mesh_eligibility import (  # noqa: E402
    HingeTarget,
    MeshEligibilityError,
    resolve_hinge_targets,
)


def hinge_layer(side: str, *, layer_id: str | None = None) -> dict:
    layer_id = layer_id or f"leg-{side}"
    return {
        "layer_id": layer_id,
        "source": {"visible": True},
        "semantic": {"canonical_role": "body.leg", "side": side},
        "rig_hint": {
            "attachment_kind": "region",
            "deform_class": "hinge",
            "candidate_bone": f"thigh.{side}",
        },
        "qa": {"status": "passed"},
    }


def rigid_layer() -> dict:
    return {
        "layer_id": "torso",
        "source": {"visible": True},
        "semantic": {"canonical_role": "body.torso", "side": "center"},
        "rig_hint": {
            "attachment_kind": "region",
            "deform_class": "rigid",
            "candidate_bone": "spine",
        },
        "qa": {"status": "passed"},
    }


def manifest_a() -> dict:
    return {
        "format": "autospine-layer-manifest",
        "format_version": 1,
        "layers": [hinge_layer("right"), hinge_layer("left")],
        "qa": {"status": "passed"},
    }


def manifest_b() -> dict:
    return {
        "format": "autospine-layer-manifest",
        "format_version": 1,
        "layers": [rigid_layer()],
        "qa": {"status": "passed"},
    }


def base_rig() -> dict:
    bones = [{"id": "root", "parent": None}]
    slots, attachments, skin = [], [], {}
    for side in ("left", "right"):
        bones.extend(
            [
                {"id": f"thigh.{side}", "parent": "root"},
                {"id": f"calf.{side}", "parent": f"thigh.{side}"},
            ]
        )
        slot_id = attachment_id = f"leg-{side}"
        slots.append(
            {
                "id": slot_id,
                "bone": f"thigh.{side}",
                "setup_attachment": attachment_id,
            }
        )
        attachments.append(
            {
                "id": attachment_id,
                "slot": slot_id,
                "type": "region",
                "source_layer_ids": [f"leg-{side}"],
            }
        )
        skin[slot_id] = [attachment_id]
    return {
        "bones": bones,
        "slots": slots,
        "attachments": attachments,
        "skins": {"default": skin},
    }


class MeshEligibilityTests(unittest.TestCase):
    def test_synthetic_a_has_two_targets_and_b_has_zero(self) -> None:
        self.assertEqual(
            (
                HingeTarget(
                    attachment_id="leg-left",
                    source_layer_id="leg-left",
                    side="left",
                    proximal_bone_id="thigh.left",
                    distal_bone_id="calf.left",
                ),
                HingeTarget(
                    attachment_id="leg-right",
                    source_layer_id="leg-right",
                    side="right",
                    proximal_bone_id="thigh.right",
                    distal_bone_id="calf.right",
                ),
            ),
            resolve_hinge_targets(manifest_a(), base_rig()),
        )
        self.assertEqual((), resolve_hinge_targets(manifest_b(), {}))

        hand = manifest_b()
        hand["layers"][0]["semantic"].update(
            canonical_role="body.hand", side="left"
        )
        self.assertEqual((), resolve_hinge_targets(hand, {}))

    def test_excluded_bilateral_parent_is_ignored(self) -> None:
        manifest = manifest_a()
        manifest["layers"].append(
            {
                "layer_id": "unsplit-parent",
                "source": {"visible": False},
                "semantic": {"canonical_role": "unknown.parent", "side": "bilateral"},
                "rig_hint": {
                    "attachment_kind": "excluded",
                    "deform_class": "hinge",
                    "candidate_bone": "unknown",
                },
                "qa": {"status": "passed"},
            }
        )
        self.assertEqual(2, len(resolve_hinge_targets(manifest, base_rig())))

    def test_unknown_unilateral_hinge_role_side_visibility_or_qa_fails(self) -> None:
        mutations = (
            ("profile-v1 role", lambda layer: layer["semantic"].update(
                canonical_role="body.arm"
            )),
            ("profile-v1 role", lambda layer: layer["semantic"].update(
                canonical_role="body.hand"
            )),
            ("profile-v1 role", lambda layer: layer["semantic"].update(
                canonical_role="body.foot"
            )),
            ("left or right", lambda layer: layer["semantic"].update(side="unknown")),
            ("visible", lambda layer: layer["source"].update(visible=False)),
            ("QA", lambda layer: layer["qa"].update(status="manual_required")),
        )
        for message, mutate in mutations:
            manifest = manifest_a()
            mutate(manifest["layers"][0])
            with self.subTest(message=message), self.assertRaisesRegex(
                MeshEligibilityError, message
            ):
                resolve_hinge_targets(manifest, base_rig())

        manifest = manifest_a()
        manifest["qa"]["status"] = "manual_required"
        with self.assertRaisesRegex(MeshEligibilityError, "Layer Manifest QA"):
            resolve_hinge_targets(manifest, base_rig())

    def test_missing_or_non_child_distal_bone_fails(self) -> None:
        rig = base_rig()
        rig["bones"] = [bone for bone in rig["bones"] if bone["id"] != "thigh.left"]
        with self.assertRaisesRegex(MeshEligibilityError, "missing proximal bone"):
            resolve_hinge_targets(manifest_a(), rig)

        rig = base_rig()
        rig["bones"] = [bone for bone in rig["bones"] if bone["id"] != "calf.left"]
        with self.assertRaisesRegex(MeshEligibilityError, "no distal child"):
            resolve_hinge_targets(manifest_a(), rig)

        rig = base_rig()
        next(b for b in rig["bones"] if b["id"] == "calf.left")["parent"] = "root"
        with self.assertRaisesRegex(MeshEligibilityError, "not a direct child"):
            resolve_hinge_targets(manifest_a(), rig)

    def test_manifest_candidate_and_base_slot_must_equal_proximal_bone(self) -> None:
        manifest = manifest_a()
        manifest["layers"][0]["rig_hint"]["candidate_bone"] = "calf.right"
        with self.assertRaisesRegex(MeshEligibilityError, "candidate bone"):
            resolve_hinge_targets(manifest, base_rig())

        rig = base_rig()
        next(slot for slot in rig["slots"] if slot["id"] == "leg-right")["bone"] = (
            "calf.right"
        )
        with self.assertRaisesRegex(MeshEligibilityError, "leg-right bone"):
            resolve_hinge_targets(manifest_a(), rig)

    def test_attachment_slot_setup_skin_and_source_must_cross_bind(self) -> None:
        changes = {
            "binding is inconsistent": lambda rig: rig["attachments"][0].update(
                type="mesh"
            ),
            "missing slot": lambda rig: rig["slots"].pop(0),
            "setup attachment": lambda rig: rig["slots"][0].update(
                setup_attachment="leg-right"
            ),
            "default skin": lambda rig: rig["skins"]["default"].update(
                {"leg-left": ["leg-right"]}
            ),
            "exactly one": lambda rig: rig["attachments"].append(
                {
                    "id": "duplicate-source",
                    "slot": "leg-left",
                    "type": "region",
                    "source_layer_ids": ["leg-left"],
                }
            ),
        }
        for message, mutate in changes.items():
            rig = base_rig()
            mutate(rig)
            with self.subTest(message=message), self.assertRaisesRegex(
                MeshEligibilityError, message
            ):
                resolve_hinge_targets(manifest_a(), rig)

        rig = base_rig()
        rig["attachments"][0]["id"] = "attachment-alias"
        rig["slots"][0]["setup_attachment"] = "attachment-alias"
        rig["skins"]["default"]["leg-left"] = ["attachment-alias"]
        with self.assertRaisesRegex(MeshEligibilityError, "binding is inconsistent"):
            resolve_hinge_targets(manifest_a(), rig)

        rig = base_rig()
        rig["attachments"][0]["slot"] = "slot-alias"
        rig["slots"][0]["id"] = "slot-alias"
        rig["skins"]["default"]["slot-alias"] = rig["skins"]["default"].pop(
            "leg-left"
        )
        with self.assertRaisesRegex(MeshEligibilityError, "slot id is inconsistent"):
            resolve_hinge_targets(manifest_a(), rig)

    def test_duplicate_layer_bone_slot_or_attachment_ids_fail(self) -> None:
        manifest = manifest_a()
        manifest["layers"].append(deepcopy(manifest["layers"][0]))
        with self.assertRaisesRegex(MeshEligibilityError, "duplicate Layer Manifest"):
            resolve_hinge_targets(manifest, base_rig())

        collections = ("bones", "slots", "attachments")
        for collection in collections:
            rig = base_rig()
            rig[collection].append(deepcopy(rig[collection][0]))
            with self.subTest(collection=collection), self.assertRaisesRegex(
                MeshEligibilityError, "duplicate id"
            ):
                resolve_hinge_targets(manifest_a(), rig)

    def test_result_is_deterministic_and_inputs_are_not_mutated(self) -> None:
        manifest, rig = manifest_a(), base_rig()
        original_manifest, original_rig = deepcopy(manifest), deepcopy(rig)
        first = resolve_hinge_targets(manifest, rig)

        self.assertEqual(original_manifest, manifest)
        self.assertEqual(original_rig, rig)

        reversed_manifest, reversed_rig = deepcopy(manifest), deepcopy(rig)
        reversed_manifest["layers"].reverse()
        reversed_rig["bones"].reverse()
        reversed_rig["slots"].reverse()
        reversed_rig["attachments"].reverse()
        reversed_manifest_before = deepcopy(reversed_manifest)
        reversed_rig_before = deepcopy(reversed_rig)
        second = resolve_hinge_targets(reversed_manifest, reversed_rig)

        self.assertEqual(first, second)
        self.assertEqual(reversed_manifest_before, reversed_manifest)
        self.assertEqual(reversed_rig_before, reversed_rig)


if __name__ == "__main__":
    unittest.main()
