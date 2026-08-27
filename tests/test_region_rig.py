"""Region-only Layer Manifest to RigIR compiler tests."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.region_rig import (  # noqa: E402
    RegionRigCompilation,
    RegionRigError,
    compile_region_rig,
)
from autospine_workbench.resolved_project import canonical_sha256  # noqa: E402
from autospine_workbench.rig_validation import RigSemanticValidator  # noqa: E402
from tests.resolved_snapshot_helpers import (  # noqa: E402
    refresh_resolved_snapshot,
    resolved_bone,
    resolved_joint,
    resolved_snapshot_from_parts,
)

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover
    Draft202012Validator = None


SHA_IMAGE = "1" * 64
SHA_OVERRIDE = "2" * 64
LAYER_ID = "layer-001-torso"


def layer_fixture(layer_id: str = LAYER_ID, draw_order: int = 7) -> dict:
    return {
        "layer_id": layer_id,
        "source": {
            "name": "torso", "index": 1, "group_path": [], "visible": True,
            "opacity": 0.5, "blend_mode": "normal",
        },
        "raster": {
            "artifact_path": f"layers/{layer_id}.png", "sha256": SHA_IMAGE,
            "canvas_size": [100, 200], "crop_bbox_xywh": [10, 20, 30, 40],
            "canvas_offset_xy": [10, 20], "channels": "RGBA",
            "alpha_mode": "straight", "color_space": "srgb", "alpha_nonzero": 900,
        },
        "semantic": {
            "source_tag": "torso", "canonical_role": "body.torso", "side": "center",
            "stratum": "body", "instance": 0, "mapping_method": "manual", "confidence": 1.0,
        },
        "derivation": {"operation": "source", "parent_layer_ids": []},
        "rig_hint": {
            "attachment_kind": "region", "deform_class": "rigid",
            "candidate_bone": "pelvis-chest",
            "pivot": {"xy": [20, 25], "method": "manual", "confidence": 1.0},
            "setup_draw_order": draw_order,
        },
        "qa": {"status": "passed", "flags": [], "notes": []},
    }


def manifest_fixture() -> dict:
    return {
        "format": "autospine-layer-manifest", "format_version": 1,
        "project_id": "sample-a", "revision": 3,
        "source": {
            "psd_sha256": "a" * 64, "audit_sha256": "b" * 64,
            "canvas": [100, 200],
            "coordinate_system": {
                "origin": "top_left", "x_axis": "right", "y_axis": "down",
                "units": "pixel", "side_naming": "character_side",
                "view_orientation": "front", "mirror_state": "not_mirrored",
            },
        },
        "layers": [layer_fixture()],
        "qa": {"status": "passed", "flags": [], "notes": []},
    }


def resolved_fixture() -> dict:
    revision = 3
    joints = [
        resolved_joint(
            "root", side="center", x=50, y=180, revision=revision
        ),
        resolved_joint(
            "pelvis", side="center", x=50, y=120, revision=revision
        ),
        resolved_joint(
            "chest", side="center", x=50, y=60, revision=revision
        ),
    ]
    bones = [
        resolved_bone(
            "root-pelvis",
            start_joint_id="root",
            end_joint_id="pelvis",
            role="humanoid.root",
        ),
        resolved_bone(
            "pelvis-chest",
            parent_id="root-pelvis",
            start_joint_id="pelvis",
            end_joint_id="chest",
            role="humanoid.spine",
        ),
    ]
    return resolved_snapshot_from_parts(
        project_id="sample-a",
        revision=revision,
        width=100,
        height=200,
        layers=[],
        joints=joints,
        bones=bones,
        base_project_sha256="c" * 64,
        override_sha256=SHA_OVERRIDE,
    )


def seal_resolved(document: dict) -> dict:
    refreshed = refresh_resolved_snapshot(document, sync_revision=True)
    document.clear()
    document.update(refreshed)
    return document


def compile_fixture(
    manifest: dict | None = None,
    resolved: dict | None = None,
    sizes: dict | None = None,
    **options,
) -> RegionRigCompilation:
    manifest = manifest or manifest_fixture()
    return compile_region_rig(
        manifest,
        resolved or resolved_fixture(),
        layer_manifest_sha256=canonical_sha256(manifest),
        image_sizes=sizes if sizes is not None else {LAYER_ID: (30, 40)},
        **options,
    )


class RegionRigCompilerTests(unittest.TestCase):
    def test_compiles_lossless_schema_valid_region_setup_deterministically(self) -> None:
        first, second = compile_fixture(), compile_fixture()
        self.assertEqual(first, second)
        rig, run = first.rig, first.run_manifest
        self.assertEqual("autospine-rig-compile-run", run["format"])
        self.assertEqual({
            "attachment_profile": "region-only", "allow_manual_required": False,
        }, run["compiler"]["config"])
        self.assertEqual(resolved_fixture()["sha256"], run["inputs"]["resolved_project_sha256"])
        self.assertEqual(SHA_OVERRIDE, run["inputs"]["override_patch_sha256"])
        self.assertEqual(canonical_sha256(run), rig["source"]["run_manifest_sha256"])
        self.assertEqual(SHA_OVERRIDE, rig["source"]["override_patch_sha256"])
        self.assertEqual(["region_attachment", "setup_draw_order"], rig["capabilities"])
        self.assertEqual([], rig["animations"])

        slot, attachment = rig["slots"][0], rig["attachments"][0]
        self.assertEqual({
            "id": LAYER_ID, "bone": "pelvis-chest", "setup_attachment": LAYER_ID,
            "setup_draw_order": 7, "blend": "normal", "color_rgba": "ffffff80",
        }, slot)
        self.assertEqual("region", attachment["type"])
        self.assertEqual("layers/layer-001-torso.png", attachment["image_path"])
        self.assertEqual(SHA_IMAGE, attachment["image_sha256"])
        self.assertEqual([LAYER_ID], attachment["source_layer_ids"])
        self.assertEqual([10, 20], attachment["canvas_offset_xy"])
        self.assertEqual([20, 25], attachment["pivot_xy"])
        self.assertEqual([30, 40], attachment["size"])
        self.assertEqual({"default": {LAYER_ID: [LAYER_ID]}}, rig["skins"])
        self.assertEqual([], RigSemanticValidator().validate(rig))
        if Draft202012Validator is not None:
            for name, document in (
                ("rig-ir-v1.schema.json", rig),
                ("rig-compile-run-v1.schema.json", run),
            ):
                schema = json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))
                Draft202012Validator(schema).validate(document)

    def test_result_is_immutable_and_returns_isolated_documents(self) -> None:
        result = compile_fixture()
        changed = result.rig
        changed["slots"][0]["bone"] = "tampered"
        self.assertEqual("pelvis-chest", result.rig["slots"][0]["bone"])
        with self.assertRaises(FrozenInstanceError):
            result._rig_json = "{}"

    def test_excluded_layers_skip_and_hidden_regions_remain_available_in_skin(self) -> None:
        manifest = manifest_fixture()
        manifest["layers"][0]["source"]["visible"] = False
        excluded = layer_fixture("layer-002-empty", 7)
        excluded["rig_hint"].update({
            "attachment_kind": "excluded", "candidate_bone": None, "pivot": None,
        })
        manifest["layers"].append(excluded)
        rig = compile_fixture(manifest).rig
        self.assertEqual([LAYER_ID], [item["id"] for item in rig["slots"]])
        self.assertIsNone(rig["slots"][0]["setup_attachment"])
        self.assertEqual([LAYER_ID], rig["skins"]["default"][LAYER_ID])

    def test_manual_required_is_strict_by_default_and_pinned_when_allowed(self) -> None:
        manifest = manifest_fixture()
        manifest["qa"] = {
            "status": "manual_required", "flags": ["LAYER_REVIEW_REQUIRED"], "notes": [],
        }
        with self.assertRaisesRegex(RegionRigError, "require.*manual review"):
            compile_fixture(manifest)
        allowed = compile_fixture(manifest, allow_manual_required=True)
        self.assertEqual("manual_required", allowed.rig["qa"]["status"])
        self.assertTrue(allowed.run_manifest["compiler"]["config"]["allow_manual_required"])

        resolved = resolved_fixture()
        unresolved = resolved["skeleton"]["joints"][2]
        unresolved["review_state"] = "unreviewed"
        unresolved.pop("decision_kind")
        unresolved.pop("decision_revision")
        seal_resolved(resolved)
        with self.assertRaisesRegex(RegionRigError, "require.*manual review"):
            compile_fixture(manifest_fixture(), resolved=resolved)
        allowed = compile_fixture(
            manifest_fixture(), resolved=resolved, allow_manual_required=True
        )
        self.assertEqual("manual_required", allowed.rig["qa"]["status"])
        self.assertEqual(canonical_sha256(allowed.run_manifest), allowed.rig["source"]["run_manifest_sha256"])

    def test_manifest_and_resolved_identity_mismatches_fail_closed(self) -> None:
        manifest, resolved = manifest_fixture(), resolved_fixture()
        with self.assertRaisesRegex(RegionRigError, "content does not match"):
            compile_region_rig(
                manifest, resolved, layer_manifest_sha256="f" * 64,
                image_sizes={LAYER_ID: (30, 40)},
            )
        corrupt = deepcopy(resolved)
        corrupt["skeleton"]["generation"]["method"] = "tampered-fixture"
        with self.assertRaisesRegex(
            RegionRigError, "self-hash|canonical snapshot content"
        ):
            compile_fixture(manifest, corrupt)
        unknown = deepcopy(resolved)
        unknown["skeleton"]["generation"]["release_approved"] = True
        seal_resolved(unknown)
        with self.assertRaisesRegex(RegionRigError, "authority field"):
            compile_fixture(manifest, unknown)
        cases = {
            "ids differ": lambda item: item.update(project_id="sample-b"),
            "revision": lambda item: item.update(revision=4),
            "canvases differ": lambda item: item["canvas"].update(width=101),
        }
        for message, mutate in cases.items():
            changed = deepcopy(resolved)
            mutate(changed)
            seal_resolved(changed)
            with self.subTest(message=message), self.assertRaisesRegex(RegionRigError, message):
                compile_fixture(manifest, changed)

    def test_unknown_or_lossy_region_fields_fail_loudly(self) -> None:
        cases = {
            "attachment kind": lambda m: m["layers"][0]["rig_hint"].update(attachment_kind="mesh"),
            "blend mode": lambda m: m["layers"][0]["source"].update(blend_mode="pass-through"),
            "unsupported blend": lambda m: m["layers"][0]["source"].update(blend_mode="multiply"),
            "does not exist": lambda m: m["layers"][0]["rig_hint"].update(candidate_bone="missing"),
            "image path is unsafe": lambda m: m["layers"][0]["raster"].update(artifact_path="../escape.png"),
        }
        for message, mutate in cases.items():
            manifest = manifest_fixture()
            mutate(manifest)
            with self.subTest(message=message), self.assertRaisesRegex(RegionRigError, message):
                compile_fixture(manifest)
        with self.assertRaisesRegex(RegionRigError, "image size"):
            compile_fixture(sizes={})
        with self.assertRaisesRegex(RegionRigError, "does not match its raster"):
            compile_fixture(sizes={LAYER_ID: (31, 40)})

    def test_diagnostic_mode_preserves_unreviewed_pivot_and_bilateral_region(self) -> None:
        manifest = manifest_fixture()
        layer = manifest["layers"][0]
        layer["semantic"]["mapping_method"] = "alias"
        layer["rig_hint"]["pivot"]["method"] = "unknown"
        layer["rig_hint"]["candidate_bone"] = None
        with self.assertRaisesRegex(RegionRigError, "require.*manual review"):
            compile_fixture(manifest)
        rig = compile_fixture(manifest, allow_manual_required=True).rig
        self.assertEqual("manual_required", rig["qa"]["status"])
        self.assertEqual("root-pelvis", rig["slots"][0]["bone"])
        self.assertEqual([20, 25], rig["attachments"][0]["pivot_xy"])

    def test_duplicate_draw_order_fails_before_slot_generation(self) -> None:
        manifest = manifest_fixture()
        manifest["layers"].append(layer_fixture("layer-002-front", 7))
        with self.assertRaisesRegex(RegionRigError, "duplicate draw order"):
            compile_fixture(
                manifest, sizes={LAYER_ID: (30, 40), "layer-002-front": (30, 40)}
            )

    def test_legacy_joint_hint_maps_uniquely_but_ambiguity_fails(self) -> None:
        manifest = manifest_fixture()
        manifest["layers"][0]["rig_hint"]["candidate_bone"] = "chest"
        rig = compile_fixture(manifest).rig
        self.assertEqual("pelvis-chest", rig["slots"][0]["bone"])

        resolved = resolved_fixture()
        resolved["skeleton"]["bones"].append(resolved_bone(
            "root-chest",
            parent_id="root-pelvis",
            start_joint_id="pelvis",
            end_joint_id="chest",
            role="humanoid.spine.alternate",
        ))
        seal_resolved(resolved)
        with self.assertRaisesRegex(RegionRigError, "ambiguous"):
            compile_fixture(manifest, resolved)


if __name__ == "__main__":
    unittest.main()
