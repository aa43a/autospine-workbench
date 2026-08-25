from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path


WORKBENCH_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = WORKBENCH_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from autospine_workbench.contracts import (  # noqa: E402
    ContractValidationError,
    normalize_override_request,
)

try:
    from jsonschema import Draft202012Validator
    from jsonschema.exceptions import ValidationError
except ImportError:  # pragma: no cover - exercised in dependency-free runtime smoke tests
    Draft202012Validator = None
    ValidationError = Exception


SCHEMA_ROOT = WORKBENCH_ROOT / "schemas"
SHA_A = "a" * 64
SHA_B = "b" * 64


def load_schema(name: str) -> dict:
    with (SCHEMA_ROOT / name).open("r", encoding="utf-8") as stream:
        return json.load(stream)


def valid_layer_manifest() -> dict:
    return {
        "format": "autospine-layer-manifest",
        "format_version": 1,
        "project_id": "sample-a",
        "revision": 0,
        "source": {
            "psd_sha256": SHA_A,
            "audit_sha256": SHA_B,
            "relative_path": "inputs/sample-a.psd",
            "canvas": [1024, 1024],
            "coordinate_system": {
                "origin": "top_left",
                "x_axis": "right",
                "y_axis": "down",
                "units": "pixel",
                "side_naming": "character_side",
                "view_orientation": "unknown",
                "mirror_state": "unknown",
            },
        },
        "layers": [
            {
                "layer_id": "layer_000",
                "source": {
                    "name": "back hair",
                    "index": 0,
                    "group_path": [],
                    "visible": True,
                    "opacity": 1.0,
                    "blend_mode": "normal",
                },
                "raster": {
                    "artifact_path": "layers/00_back_hair.png",
                    "sha256": SHA_A,
                    "canvas_size": [1024, 1024],
                    "crop_bbox_xywh": [201, 83, 626, 465],
                    "canvas_offset_xy": [201, 83],
                    "channels": "RGBA",
                    "alpha_mode": "straight",
                    "color_space": "srgb",
                    "alpha_nonzero": 123259,
                    "component_areas": [116231, 40],
                },
                "semantic": {
                    "source_tag": "back hair",
                    "canonical_role": "back_hair",
                    "side": "center",
                    "stratum": "back",
                    "instance": 0,
                    "mapping_method": "exact",
                    "confidence": 1.0,
                },
                "derivation": {
                    "operation": "source",
                    "parent_layer_ids": [],
                },
                "rig_hint": {
                    "attachment_kind": "region",
                    "deform_class": "hair",
                    "candidate_bone": "head",
                    "pivot": None,
                    "setup_draw_order": 0,
                },
                "qa": {"status": "passed", "flags": [], "notes": []},
            }
        ],
        "qa": {"status": "manual_required", "flags": ["PIVOT_PENDING"], "notes": []},
    }


def valid_rig_ir() -> dict:
    return {
        "format": "autospine-rig-ir",
        "format_version": 1,
        "source": {
            "run_manifest_sha256": SHA_A,
            "layer_manifest_sha256": SHA_B,
        },
        "canvas": {
            "width": 1024,
            "height": 1024,
            "origin": "top_left",
            "x_axis": "right",
            "y_axis": "down",
            "units": "pixel",
        },
        "capabilities": [
            "region_attachment",
            "bone_translate",
            "bone_rotate",
            "setup_draw_order",
        ],
        "unsupported_feature_policy": "fail",
        "bones": [
            {
                "id": "root",
                "parent": None,
                "setup": {
                    "x": 512,
                    "y": 900,
                    "rotation_deg": 0,
                    "scale_x": 1,
                    "scale_y": 1,
                    "length": 0,
                },
                "inference": {"method": "manual", "confidence": 1.0},
            }
        ],
        "slots": [
            {
                "id": "slot_body",
                "bone": "root",
                "setup_attachment": "att_body",
                "setup_draw_order": 0,
                "blend": "normal",
                "color_rgba": "ffffffff",
            }
        ],
        "attachments": [
            {
                "id": "att_body",
                "slot": "slot_body",
                "type": "region",
                "image_path": "layers/body.png",
                "image_sha256": SHA_A,
                "source_layer_ids": ["layer_000"],
                "canvas_offset_xy": [100, 100],
                "pivot_xy": [512, 900],
                "size": [500, 800],
            }
        ],
        "skins": {"default": {"slot_body": ["att_body"]}},
        "animations": [
            {
                "id": "setup",
                "duration": 0,
                "loop": False,
                "timelines": [],
            }
        ],
        "qa": {"status": "passed", "checks": [], "manual_override_ids": []},
    }


def valid_override_patch() -> dict:
    return {
        "base_revision": 0,
        "joint_overrides": {
            "shoulder.L": {
                "x": 320.5,
                "y": 410.25,
                "confidence": 1.0,
                "reason": "reviewed against arm overlap",
            }
        },
        "layer_overrides": {
            "layer_000": {
                "canonical_role": "upper_arm",
                "side": "left",
                "disposition": "keep",
                "pivot_xy": [320.5, 410.25],
                "visible": True,
                "notes": "character-side left",
            }
        },
        "notes": "first review pass",
    }


class JsonSchemaContractTests(unittest.TestCase):
    def test_schema_documents_are_parseable_draft_2020_12(self) -> None:
        for name in (
            "layer-manifest-v1.schema.json",
            "rig-ir-v1.schema.json",
            "override-patch-v1.schema.json",
            "override-patch-v2.schema.json",
            "override-patch-v3.schema.json",
            "joint-candidates-v1.schema.json",
            "pose-observations-v1.schema.json",
            "alpha-geometry-evidence-v1.schema.json",
        ):
            schema = load_schema(name)
            self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
            self.assertTrue(schema["$id"].endswith(name))

    @unittest.skipIf(Draft202012Validator is None, "install the 'test' extra for JSON Schema checks")
    def test_minimum_v1_examples_validate(self) -> None:
        examples = (
            ("layer-manifest-v1.schema.json", valid_layer_manifest()),
            ("rig-ir-v1.schema.json", valid_rig_ir()),
            ("override-patch-v1.schema.json", valid_override_patch()),
        )
        for name, document in examples:
            with self.subTest(schema=name):
                schema = load_schema(name)
                Draft202012Validator.check_schema(schema)
                Draft202012Validator(schema).validate(document)

    @unittest.skipIf(Draft202012Validator is None, "install the 'test' extra for JSON Schema checks")
    def test_contract_rejects_traversal_and_unknown_patch_fields(self) -> None:
        layer_document = valid_layer_manifest()
        layer_document["layers"][0]["raster"]["artifact_path"] = "../outside.png"
        layer_validator = Draft202012Validator(load_schema("layer-manifest-v1.schema.json"))
        with self.assertRaises(ValidationError):
            layer_validator.validate(layer_document)

        rig_document = valid_rig_ir()
        rig_document["attachments"][0]["image_path"] = "C:/outside.png"
        rig_validator = Draft202012Validator(load_schema("rig-ir-v1.schema.json"))
        with self.assertRaises(ValidationError):
            rig_validator.validate(rig_document)

        patch = valid_override_patch()
        patch["force"] = True
        patch_validator = Draft202012Validator(load_schema("override-patch-v1.schema.json"))
        with self.assertRaises(ValidationError):
            patch_validator.validate(patch)

    @unittest.skipIf(Draft202012Validator is None, "install the 'test' extra for JSON Schema checks")
    def test_layer_side_uses_character_semantics_without_prefixed_values(self) -> None:
        validator = Draft202012Validator(load_schema("layer-manifest-v1.schema.json"))
        document = valid_layer_manifest()
        document["layers"][0]["semantic"]["side"] = "left"
        validator.validate(document)
        document["layers"][0]["semantic"]["side"] = "character_left"
        with self.assertRaises(ValidationError):
            validator.validate(document)


class PythonOverrideContractTests(unittest.TestCase):
    def test_canonical_patch_normalizes_without_losing_visible(self) -> None:
        patch = valid_override_patch()
        patch["layer_overrides"]["layer_000"]["candidate_bone"] = "shoulder-elbow.L"
        base_revision, normalized = normalize_override_request(
            patch,
            project_id="sample-a",
            current_revision=0,
            joint_ids={"shoulder.L"},
            layer_ids={"layer_000"},
            canvas_width=1024,
            canvas_height=1024,
        )
        self.assertEqual(base_revision, 0)
        self.assertEqual(normalized["revision"], 0)
        self.assertEqual(normalized["joint_overrides"]["shoulder.L"]["x"], 320.5)
        self.assertIs(normalized["layer_overrides"]["layer_000"]["visible"], True)
        self.assertEqual(
            "shoulder-elbow.L",
            normalized["layer_overrides"]["layer_000"]["candidate_bone"],
        )

    def test_candidate_bone_requires_a_safe_identifier(self) -> None:
        patch = valid_override_patch()
        patch["layer_overrides"]["layer_000"]["candidate_bone"] = "../escape"
        with self.assertRaises(ContractValidationError) as caught:
            normalize_override_request(
                patch,
                project_id="sample-a",
                current_revision=0,
                joint_ids={"shoulder.L"},
                layer_ids={"layer_000"},
                canvas_width=1024,
                canvas_height=1024,
            )
        self.assertIn("format", {issue.code for issue in caught.exception.issues})

    def test_unknown_ids_and_non_finite_coordinates_are_rejected(self) -> None:
        patch = valid_override_patch()
        patch["joint_overrides"] = {"unknown": {"x": float("nan"), "y": 2}}
        with self.assertRaises(ContractValidationError) as caught:
            normalize_override_request(
                patch,
                project_id="sample-a",
                current_revision=0,
                joint_ids={"shoulder.L"},
                layer_ids={"layer_000"},
                canvas_width=1024,
                canvas_height=1024,
            )
        codes = {issue.code for issue in caught.exception.issues}
        self.assertIn("unknown_id", codes)

    def test_patch_is_not_mutated_during_normalization(self) -> None:
        patch = valid_override_patch()
        before = copy.deepcopy(patch)
        normalize_override_request(
            patch,
            project_id="sample-a",
            current_revision=0,
            joint_ids={"shoulder.L"},
            layer_ids={"layer_000"},
            canvas_width=1024,
            canvas_height=1024,
        )
        self.assertEqual(patch, before)


if __name__ == "__main__":
    unittest.main()
