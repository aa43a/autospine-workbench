"""Optional Draft 2020-12 instances for ReviewedSeamAnchorSet v1."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
for item in (ROOT, ROOT / "src"):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from autospine_workbench.reviewed_seam_anchor_set_compiler import (
    compile_reviewed_seam_anchor_set,
)
from tests.reviewed_seam_anchor_set_helpers import reviewed_set_inputs

try:
    from jsonschema import Draft202012Validator
    from jsonschema.exceptions import ValidationError
except ImportError:  # pragma: no cover - exercised without the optional extra
    Draft202012Validator = None
    ValidationError = Exception

@unittest.skipIf(Draft202012Validator is None, "jsonschema is optional")
class ReviewedSeamAnchorSetSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        schema = json.loads((
            ROOT / "schemas" / "reviewed-seam-anchor-set-v1.schema.json"
        ).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        cls.validator = Draft202012Validator(schema)
        candidate, decision, rig = reviewed_set_inputs()
        cls.valid = compile_reviewed_seam_anchor_set(
            candidate, decision, rig
        ).document

    def assert_schema_rejects(self, mutate):
        document = deepcopy(self.valid)
        mutate(document)
        with self.assertRaises(ValidationError):
            self.validator.validate(document)

    def test_compiled_region_and_mesh_instances_validate(self):
        self.validator.validate(self.valid)
        candidate, decision, rig = reviewed_set_inputs(
            mesh_id="leg.left"
        )
        mesh_document = compile_reviewed_seam_anchor_set(
            candidate, decision, rig
        ).document
        self.assertTrue(any(
            endpoint["attachment_type"] == "mesh"
            for relationship in mesh_document["relationships"]
            for pair in relationship["anchors"]
            for endpoint in (pair["parent"], pair["child"])
        ))
        self.validator.validate(mesh_document)

    def test_fixed_identity_order_and_claims_reject_mutation(self):
        cases = (
            lambda row: row.__setitem__("extra", True),
            lambda row: row["source"].__setitem__("extra", True),
            lambda row: row["source"].__setitem__("review_revision", 0),
            lambda row: row["relationships"].reverse(),
            lambda row: row["compiler"].__setitem__(
                "candidate_reselection", "allowed"
            ),
            lambda row: row["semantics"].__setitem__(
                "motion_or_clip_input_admitted", True
            ),
            lambda row: row["claims"].__setitem__(
                "dynamic_seam_safety", True
            ),
            lambda row: row["release_gate"].__setitem__("status", "ready"),
        )
        for mutate in cases:
            with self.subTest(mutate=mutate):
                self.assert_schema_rejects(mutate)

    def test_anchor_count_pair_id_and_locator_union_are_strict(self):
        def one_anchor(row):
            row["relationships"][0]["anchors"] = row["relationships"][0][
                "anchors"
            ][:1]

        def wrong_pair(row):
            row["relationships"][0]["anchors"][0]["pair_id"] = "pair.000"

        def mixed_locator(row):
            row["relationships"][0]["anchors"][0]["parent"][
                "triangle_index"
            ] = 0

        def illegal_mesh_weight(row):
            for relationship in row["relationships"]:
                for pair in relationship["anchors"]:
                    for endpoint in (pair["parent"], pair["child"]):
                        if endpoint["attachment_type"] == "mesh":
                            endpoint["weights_q65535"][0] = 65536
                            return
            parent = row["relationships"][0]["anchors"][0]["parent"]
            parent.clear()
            parent.update({
                "attachment_id": "mesh-test",
                "attachment_type": "mesh",
                "locator_type": "mesh-barycentric-q65535",
                "triangle_index": 0,
                "vertex_indices": [0, 1, 2],
                "weights_q65535": [65536, 0, 0],
            })

        for mutate in (one_anchor, wrong_pair, mixed_locator,
                       illegal_mesh_weight):
            with self.subTest(mutate=mutate):
                self.assert_schema_rejects(mutate)


if __name__ == "__main__":
    unittest.main()
