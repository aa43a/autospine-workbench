from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.alpha_evidence_validation import (  # noqa: E402
    AlphaEvidenceValidationError,
    require_valid_alpha_geometry_evidence,
    validate_alpha_geometry_evidence,
)
from autospine_workbench.resolved_project import canonical_sha256  # noqa: E402

try:
    from jsonschema import Draft202012Validator
    from jsonschema.exceptions import ValidationError
except ImportError:  # pragma: no cover - dependency-free runtime
    Draft202012Validator = None
    ValidationError = Exception


SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
SHA_D = "d" * 64
JOINTS = {"shoulder.left", "elbow.left", "wrist.left"}
LAYERS = {"arm.left", "torso"}


def refresh_identity(document: dict) -> None:
    analysis = document["analysis"]
    analysis["input_sha256"] = canonical_sha256(
        {
            "project_id": document["project_id"],
            "source": document["source"],
            "layers": document["layers"],
        }
    )
    analysis["run_sha256"] = canonical_sha256(
        {
            "input_sha256": analysis["input_sha256"],
            "provider": analysis["provider"],
            "provider_version": analysis["provider_version"],
            "config_sha256": analysis["config_sha256"],
        }
    )


def valid_document() -> dict:
    layers = [
        {
            "layer_id": "arm.left",
            "raster_sha256": SHA_A,
            "canonical_role": "upper_arm",
            "side": "left",
            "disposition": "keep",
            "alpha_threshold": 8,
            "foreground_area": 400,
            "components": [{"component_id": 0, "area": 400, "bbox_xywh": [10, 10, 20, 20]}],
        },
        {
            "layer_id": "torso",
            "raster_sha256": SHA_B,
            "canonical_role": "torso",
            "side": "center",
            "disposition": "keep",
            "alpha_threshold": 8,
            "foreground_area": 400,
            "components": [{"component_id": 0, "area": 400, "bbox_xywh": [20, 10, 20, 20]}],
        },
    ]
    source = {
        "base_project_sha256": SHA_C,
        "source_image_sha256": SHA_D,
        "audit_sha256": SHA_A,
        "pose_observations_sha256": SHA_B,
    }
    document = {
        "format": "autospine-alpha-geometry-evidence",
        "format_version": 1,
        "project_id": "sample-a",
        "source": source,
        "analysis": {
            "provider": "alpha-path-contact",
            "provider_version": "1",
            "input_sha256": "0" * 64,
            "config_sha256": SHA_C,
            "run_sha256": "0" * 64,
        },
        "coordinate_system": {
            "origin": "top_left",
            "x_axis": "right",
            "y_axis": "down",
            "units": "pixel",
            "side_naming": "character_side",
        },
        "layers": layers,
        "paths": [
            {
                "path_id": "arm.left.path.000",
                "limb_id": "arm.left",
                "status": "valid",
                "joint_ids": ["shoulder.left", "elbow.left", "wrist.left"],
                "layer_id": "arm.left",
                "component_id": 0,
                "anchors": {
                    "proximal": {
                        "joint_id": "shoulder.left",
                        "input_xy": [20, 20],
                        "projected_xy": [20, 20],
                        "residual_px": 0,
                    },
                    "hinge": {
                        "joint_id": "elbow.left",
                        "input_xy": [30, 40],
                        "projected_xy": [30, 40],
                        "residual_px": 0,
                    },
                    "distal": {
                        "joint_id": "wrist.left",
                        "input_xy": [40, 60],
                        "projected_xy": [40, 60],
                        "residual_px": 0,
                    },
                },
                "polyline_xy": [[20, 20], [30, 40], [40, 60]],
                "length_px": 44.7214,
                "min_clearance_px": 2,
                "median_clearance_px": 4,
                "hinge_candidate_xy": [30, 40],
                "error_radius_px": 2,
                "budgets": {
                    "max_raster_pixels": 400000,
                    "max_search_nodes": 250000,
                    "raster_pixels": 484,
                    "search_nodes": 120,
                },
                "flags": ["CHAMFER_CLEARANCE_APPROXIMATION"],
            }
        ],
        "contacts": [
            {
                "contact_id": "shoulder.left.contact.000",
                "joint_id": "shoulder.left",
                "relation": "torso_arm",
                "layer_ids": ["torso", "arm.left"],
                "mode": "overlap",
                "area": 100,
                "bbox_xywh": [20, 18, 10, 10],
                "centroid_xy": [24.5, 22.5],
                "variance_xy": [8.25, 8.25],
                "representative_xy": [24, 22],
                "error_radius_px": 4.062019,
                "overlap_ratios": [0.25, 0.25],
                "gap_distance_px": 0,
                "endpoints_xy": [[24, 22], [24, 22]],
                "flags": [],
            }
        ],
        "observability": {
            "shoulder.left": {
                "status": "visible",
                "path_ids": ["arm.left.path.000"],
                "contact_ids": ["shoulder.left.contact.000"],
                "flags": [],
            },
            "elbow.left": {
                "status": "visible",
                "path_ids": ["arm.left.path.000"],
                "contact_ids": [],
                "flags": [],
            },
            "wrist.left": {
                "status": "visible",
                "path_ids": ["arm.left.path.000"],
                "contact_ids": [],
                "flags": [],
            },
        },
        "qa": {"status": "manual_required", "flags": ["MANUAL_REVIEW_REQUIRED"]},
    }
    refresh_identity(document)
    return document


def validate(document: object):
    return validate_alpha_geometry_evidence(
        document,
        project_id="sample-a",
        joint_ids=JOINTS,
        layer_ids=LAYERS,
        canvas_width=100,
        canvas_height=200,
    )


class AlphaEvidenceSemanticTests(unittest.TestCase):
    def test_valid_document_is_content_addressable_and_fail_closed(self) -> None:
        document = valid_document()
        self.assertEqual([], validate(document))
        require_valid_alpha_geometry_evidence(
            document,
            project_id="sample-a",
            joint_ids=JOINTS,
            layer_ids=LAYERS,
            canvas_width=100,
            canvas_height=200,
        )
        broken = copy.deepcopy(document)
        broken["analysis"]["provider_version"] = "2"
        self.assertIn("identity", {issue.code for issue in validate(broken)})
        with self.assertRaises(AlphaEvidenceValidationError) as caught:
            require_valid_alpha_geometry_evidence(
                broken,
                project_id="sample-a",
                joint_ids=JOINTS,
                layer_ids=LAYERS,
                canvas_width=100,
                canvas_height=200,
            )
        self.assertTrue(caught.exception.issues[0].to_dict()["path"])

    def test_layer_semantics_are_part_of_deterministic_input_identity(self) -> None:
        for field, changed_value in (
            ("canonical_role", "lower_arm"),
            ("side", "right"),
            ("disposition", "review"),
        ):
            with self.subTest(field=field):
                document = valid_document()
                original_input = document["analysis"]["input_sha256"]
                document["layers"][0][field] = changed_value
                self.assertIn("identity", {issue.code for issue in validate(document)})

                refresh_identity(document)
                self.assertEqual([], validate(document))
                self.assertNotEqual(original_input, document["analysis"]["input_sha256"])

    def test_pose_hash_is_required_only_when_paths_exist(self) -> None:
        document = valid_document()
        document["source"].pop("pose_observations_sha256")
        refresh_identity(document)
        self.assertIn("required", {issue.code for issue in validate(document)})

        document["paths"] = []
        for item in document["observability"].values():
            item["path_ids"] = []
        refresh_identity(document)
        self.assertEqual([], validate(document))

    def test_cross_references_unique_ids_and_joint_order_are_checked(self) -> None:
        document = valid_document()
        path = document["paths"][0]
        path["component_id"] = 9
        path["joint_ids"] = ["shoulder.left", "missing", "wrist.left"]
        path["anchors"]["hinge"]["joint_id"] = "shoulder.left"
        document["contacts"][0]["layer_ids"] = ["torso", "torso"]
        document["paths"].append(copy.deepcopy(path))
        codes = {issue.code for issue in validate(document)}
        self.assertTrue({"component", "unknown_joint", "joint", "shape", "id"}.issubset(codes))

    def test_non_finite_out_of_canvas_unknown_and_unsorted_values_fail(self) -> None:
        document = valid_document()
        document["paths"][0]["anchors"]["hinge"]["input_xy"] = [float("nan"), 2]
        document["paths"][0]["length_px"] = -1
        document["contacts"][0]["representative_xy"] = [101, 20]
        document["contacts"][0]["flags"] = ["Z_FLAG", "A_FLAG"]
        document["contacts"][0]["surprise"] = True
        codes = {issue.code for issue in validate(document)}
        self.assertTrue({"coordinate", "bounds", "order", "unknown_field"}.issubset(codes))

    def test_contact_threshold_ratio_and_gap_endpoint_semantics_are_checked(self) -> None:
        document = valid_document()
        for layer in document["layers"]:
            layer["foreground_area"] = 20_000
            layer["components"][0]["area"] = 20_000
        contact = document["contacts"][0]
        contact["area"] = 16
        contact["overlap_ratios"] = [0.25, 0.25]
        refresh_identity(document)
        codes = {issue.code for issue in validate(document)}
        self.assertTrue({"contact", "identity"}.issubset(codes))

        contact.update(
            mode="gap",
            area=0,
            overlap_ratios=[0, 0],
            gap_distance_px=2,
            endpoints_xy=[[20, 20], [23, 20]],
        )
        self.assertIn("identity", {issue.code for issue in validate(document)})

    def test_malformed_nested_json_returns_issues_instead_of_crashing(self) -> None:
        document = valid_document()
        document["paths"][0]["joint_ids"] = [[], {}, None]
        document["contacts"][0]["layer_ids"] = [[], {}]
        document["contacts"][0]["joint_id"] = []
        document["layers"][0]["layer_id"] = []
        document["source"]["audit_sha256"] = float("nan")
        self.assertTrue(validate(document))


@unittest.skipIf(Draft202012Validator is None, "install the test extra for schema checks")
class AlphaEvidenceSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with (ROOT / "schemas" / "alpha-geometry-evidence-v1.schema.json").open(
            "r", encoding="utf-8"
        ) as stream:
            cls.schema = json.load(stream)
        Draft202012Validator.check_schema(cls.schema)
        cls.validator = Draft202012Validator(cls.schema)

    def test_valid_document_matches_schema(self) -> None:
        self.validator.validate(valid_document())

    def test_schema_rejects_unknown_fields_and_missing_pose_provenance(self) -> None:
        unknown = valid_document()
        unknown["contacts"][0]["surprise"] = True
        with self.assertRaises(ValidationError):
            self.validator.validate(unknown)

        missing_pose = valid_document()
        missing_pose["source"].pop("pose_observations_sha256")
        with self.assertRaises(ValidationError):
            self.validator.validate(missing_pose)


if __name__ == "__main__":
    unittest.main()
