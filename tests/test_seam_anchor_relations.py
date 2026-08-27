"""Static semantic relationship inventory for reviewed seam anchors."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.resolved_project import canonical_sha256  # noqa: E402
from autospine_workbench.seam_anchor_relations import (  # noqa: E402
    SeamAnchorRelationError,
    build_seam_relationship_inventory,
)


def _layer(layer_id, role, side, *, visible=True):
    return {
        "layer_id": layer_id,
        "source": {"visible": visible},
        "semantic": {"canonical_role": role, "side": side},
    }


def _documents():
    specs = (
        ("torso", "body.torso", "center"),
        ("pelvis", "body.pelvis", "bilateral"),
        ("arm.left", "body.arm.upper", "left"),
        ("arm.right", "body.arm.upper", "right"),
        ("leg.left", "body.leg", "left"),
        ("leg.right", "body.leg", "right"),
        ("foot.left", "body.foot", "left"),
        ("foot.right", "body.foot", "right"),
    )
    manifest = {
        "format": "autospine-layer-manifest",
        "format_version": 1,
        "layers": [_layer(*spec) for spec in specs],
        "qa": {"status": "passed"},
    }
    slots = [{"id": name, "setup_attachment": name} for name, _, _ in specs]
    attachments = [{
        "id": name, "slot": name, "type": "region",
        "source_layer_ids": [name],
    } for name, _, _ in specs]
    rig = {
        "format": "autospine-rig-ir",
        "format_version": 1,
        "source": {"layer_manifest_sha256": canonical_sha256(manifest)},
        "slots": slots,
        "attachments": attachments,
        "skins": {"default": {name: [name] for name, _, _ in specs}},
        "qa": {"status": "passed"},
    }
    return manifest, rig


def _rebind(manifest, rig):
    rig["source"]["layer_manifest_sha256"] = canonical_sha256(manifest)


def _row(rows, relation, side):
    return next(
        item for item in rows
        if item["relation"] == relation and item["side"] == side
    )


def _remove_sources(manifest, rig, source_ids):
    manifest["layers"] = [
        item for item in manifest["layers"] if item["layer_id"] not in source_ids
    ]
    attachment_ids = {
        item["id"] for item in rig["attachments"]
        if set(item["source_layer_ids"]) & set(source_ids)
    }
    rig["attachments"] = [
        item for item in rig["attachments"] if item["id"] not in attachment_ids
    ]
    rig["slots"] = [item for item in rig["slots"] if item["id"] not in attachment_ids]
    for attachment_id in attachment_ids:
        rig["skins"]["default"].pop(attachment_id)
    _rebind(manifest, rig)


class SeamAnchorRelationTests(unittest.TestCase):
    def test_fixed_six_rows_bind_neutral_parents_without_guessing_side(self):
        manifest, rig = _documents()
        rows = build_seam_relationship_inventory(manifest, rig)
        self.assertEqual(
            [
                ("seam.torso_arm.left", "torso_arm", "shoulder.left", "left"),
                ("seam.torso_arm.right", "torso_arm", "shoulder.right", "right"),
                ("seam.pelvis_leg.left", "pelvis_leg", "hip.left", "left"),
                ("seam.pelvis_leg.right", "pelvis_leg", "hip.right", "right"),
                ("seam.leg_foot.left", "leg_foot", "ankle.left", "left"),
                ("seam.leg_foot.right", "leg_foot", "ankle.right", "right"),
            ],
            [(row["relationship_id"], row["relation"], row["joint"], row["side"])
             for row in rows],
        )
        self.assertTrue(all(len(row["candidate_pairs"]) == 1 for row in rows))
        self.assertTrue(all(row["reason_codes"] == [] for row in rows))

    def test_missing_role_keeps_rows_and_explicitly_explains_absence(self):
        manifest, rig = _documents()
        _remove_sources(manifest, rig, {"foot.left", "foot.right"})
        rows = build_seam_relationship_inventory(manifest, rig)
        for side in ("left", "right"):
            row = _row(rows, "leg_foot", side)
            self.assertEqual([], row["candidate_pairs"])
            self.assertIn("CHILD_ROLE_MISSING", row["reason_codes"])
            self.assertIn("NO_SUPPORTED_CANDIDATE_PAIR", row["reason_codes"])
        self.assertEqual(6, len(rows))

    def test_multilayer_side_conflict_is_not_resolved_by_screen_position(self):
        manifest, rig = _documents()
        left = next(item for item in rig["attachments"] if item["id"] == "arm.left")
        left["source_layer_ids"] = ["arm.right", "arm.left"]
        rows = build_seam_relationship_inventory(manifest, rig)
        for side in ("left", "right"):
            row = _row(rows, "torso_arm", side)
            self.assertIn("CHILD_SOURCE_SIDE_CONFLICT", row["reason_codes"])
            self.assertIn("CHILD_SOURCE_LAYER_CROSSWIRE", row["reason_codes"])
        self.assertEqual([], _row(rows, "torso_arm", "left")["candidate_pairs"])

    def test_single_role_string_with_two_families_is_a_conflict(self):
        manifest, rig = _documents()
        next(item for item in manifest["layers"]
             if item["layer_id"] == "arm.left")["semantic"][
                 "canonical_role"
             ] = "body.torso.arm"
        _rebind(manifest, rig)
        row = _row(build_seam_relationship_inventory(manifest, rig),
                   "torso_arm", "left")
        self.assertEqual([], row["candidate_pairs"])
        self.assertIn("CHILD_SOURCE_ROLE_CONFLICT", row["reason_codes"])

    def test_multiple_semantic_candidates_are_all_retained_and_sorted(self):
        manifest, rig = _documents()
        manifest["layers"].append(_layer("sleeve.left", "body.arm.lower", "left"))
        rig["slots"].append({"id": "z-sleeve", "setup_attachment": "z-sleeve"})
        rig["attachments"].append({
            "id": "z-sleeve", "slot": "z-sleeve", "type": "mesh",
            "source_layer_ids": ["sleeve.left"],
        })
        rig["skins"]["default"]["z-sleeve"] = ["z-sleeve"]
        _rebind(manifest, rig)
        row = _row(
            build_seam_relationship_inventory(manifest, rig), "torso_arm", "left"
        )
        self.assertEqual(
            ["arm.left", "z-sleeve"],
            [item["child_attachment_id"] for item in row["candidate_pairs"]],
        )
        self.assertIn("MULTIPLE_CANDIDATE_PAIRS", row["reason_codes"])

    def test_reordered_inputs_and_multilayer_sources_have_identical_output(self):
        manifest, rig = _documents()
        manifest["layers"].append(_layer("torso.detail", "body.torso", "center"))
        torso = next(item for item in rig["attachments"] if item["id"] == "torso")
        torso["source_layer_ids"] = ["torso.detail", "torso"]
        _rebind(manifest, rig)
        expected = build_seam_relationship_inventory(manifest, rig)

        reordered_manifest, reordered_rig = deepcopy(manifest), deepcopy(rig)
        reordered_manifest["layers"].reverse()
        reordered_rig["slots"].reverse()
        reordered_rig["attachments"].reverse()
        next(item for item in reordered_rig["attachments"]
             if item["id"] == "torso")["source_layer_ids"].reverse()
        _rebind(reordered_manifest, reordered_rig)
        self.assertEqual(
            expected,
            build_seam_relationship_inventory(reordered_manifest, reordered_rig),
        )

    def test_nonvisible_unsupported_and_mesh_mesh_pairs_fail_closed(self):
        manifest, rig = _documents()
        next(item for item in rig["slots"]
             if item["id"] == "arm.left")["setup_attachment"] = None
        left = _row(build_seam_relationship_inventory(manifest, rig),
                    "torso_arm", "left")
        self.assertIn("CHILD_ATTACHMENT_NOT_SETUP_VISIBLE", left["reason_codes"])
        self.assertEqual([], left["candidate_pairs"])

        manifest, rig = _documents()
        next(item for item in rig["attachments"]
             if item["id"] == "foot.right")["type"] = "clipping"
        foot = _row(build_seam_relationship_inventory(manifest, rig),
                    "leg_foot", "right")
        self.assertIn("CHILD_ATTACHMENT_TYPE_UNSUPPORTED", foot["reason_codes"])

        manifest, rig = _documents()
        for identifier in ("torso", "arm.left"):
            next(item for item in rig["attachments"]
                 if item["id"] == identifier)["type"] = "mesh"
        seam = _row(build_seam_relationship_inventory(manifest, rig),
                    "torso_arm", "left")
        self.assertIn("MESH_MESH_UNSUPPORTED", seam["reason_codes"])
        self.assertEqual([], seam["candidate_pairs"])

    def test_leg_foot_requires_explicit_same_side_parent(self):
        manifest, rig = _documents()
        next(item for item in manifest["layers"]
             if item["layer_id"] == "leg.left")["semantic"]["side"] = "bilateral"
        _rebind(manifest, rig)
        row = _row(build_seam_relationship_inventory(manifest, rig),
                   "leg_foot", "left")
        self.assertIn("PARENT_SIDE_UNAVAILABLE", row["reason_codes"])
        self.assertEqual([], row["candidate_pairs"])

    def test_stale_manifest_binding_is_rejected(self):
        manifest, rig = _documents()
        manifest["layers"].reverse()
        with self.assertRaisesRegex(SeamAnchorRelationError, "another Layer Manifest"):
            build_seam_relationship_inventory(manifest, rig)

    def test_candidate_pair_budget_stops_before_cross_product(self):
        manifest, rig = _documents()
        manifest["layers"].append(_layer(
            "sleeve.left", "body.arm.lower", "left"
        ))
        rig["slots"].append({
            "id": "sleeve.left", "setup_attachment": "sleeve.left"
        })
        rig["attachments"].append({
            "id": "sleeve.left", "slot": "sleeve.left", "type": "region",
            "source_layer_ids": ["sleeve.left"],
        })
        rig["skins"]["default"]["sleeve.left"] = ["sleeve.left"]
        _rebind(manifest, rig)
        with patch(
            "autospine_workbench.seam_anchor_relations."
            "MAX_RELATION_CANDIDATE_PAIRS", 1
        ):
            row = _row(build_seam_relationship_inventory(manifest, rig),
                       "torso_arm", "left")
        self.assertEqual([], row["candidate_pairs"])
        self.assertIn("RELATION_CANDIDATE_PAIR_BUDGET_EXCEEDED",
                      row["reason_codes"])


if __name__ == "__main__":
    unittest.main()
