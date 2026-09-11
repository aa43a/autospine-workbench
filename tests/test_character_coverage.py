"""Source accounting must not equate rendering with completed binding."""

from copy import deepcopy
import unittest

from autospine_workbench.automation.character_coverage import build_coverage, validate_coverage


class CharacterCoverageTests(unittest.TestCase):
    def setUp(self):
        self.source = {"layers": [{"layer_id": name, "name": name} for name in ("arm", "legs", "face", "extra")]}
        self.draft = {"records": [{"layer_id": r["layer_id"], "action": "pending", "option_id": None}
                                   for r in self.source["layers"]]}
        self.bindings = {"bindings": [{"layer_id": r["layer_id"], "options": []} for r in self.source["layers"]]}
        self.expanded = [self.source["layers"][0],
                         {"layer_id": "left", "source_layer_id": "legs"},
                         {"layer_id": "right", "source_layer_id": "legs"},
                         {"layer_id": "residual", "source_layer_id": "legs"},
                         *self.source["layers"][2:]]
        self.scope = {"regions": [{"id": name, "source_mesh_status": state} for name, state in (
            ("arm", "candidate"), ("left", "candidate"), ("right", "candidate"),
            ("residual", "rigid_context"), ("face", "rigid_context"))],
            "review_items": [{"layer_id": "legs", "reason_code": "residual_binding_required"}],
            "source_addresses": {"resolved_project_sha256": "a" * 64}}

    def build(self):
        return build_coverage(self.source, self.draft, self.bindings, self.expanded, self.scope, "b" * 64)

    def test_partition_residual_remains_partial_and_missing_layer_counted(self):
        doc = self.build()
        self.assertEqual([r["state"] for r in doc["layers"]],
                         ["weighted_candidate", "partial", "static_reference", "missing"])
        self.assertEqual(doc["summary"]["source_layers"], 4)
        self.assertEqual(doc["summary"]["output_regions"], 5)
        self.assertEqual(len(validate_coverage(doc)), 64)
        self.assertFalse(doc["full_character_animation"])

    def test_explicit_rigid_binding_is_distinct_from_static_context(self):
        self.draft["records"][2].update(action="bind", option_id="head")
        self.bindings["bindings"][2]["options"] = [{"id": "head", "mode": "rigid"}]
        self.assertEqual(self.build()["layers"][2]["state"], "rigid_reviewed")

    def test_missing_partition_cannot_claim_fully_weighted(self):
        self.scope["regions"] = self.scope["regions"][:2]
        row = self.build()["layers"][1]
        self.assertEqual(row["state"], "partial")
        self.assertEqual(row["missing_region_ids"], ["right", "residual"])

    def test_excluded_and_hidden_do_not_count_as_missing(self):
        self.draft["records"][3]["action"] = "exclude"
        self.assertEqual(self.build()["layers"][3]["state"], "excluded")
        self.draft["records"][3]["action"] = "pending"
        self.source["layers"][3]["empty"] = True
        self.assertEqual(self.build()["layers"][3]["state"], "not_visible")

    def test_unknown_and_duplicate_output_rejected(self):
        self.scope["regions"].append({"id": "bogus", "source_mesh_status": "candidate"})
        with self.assertRaisesRegex(ValueError, "unknown_region"): self.build()
        self.scope["regions"][-1] = deepcopy(self.scope["regions"][0])
        with self.assertRaisesRegex(ValueError, "duplicate_identity"): self.build()

    def test_rendered_exclusion_rejected(self):
        self.draft["records"][0]["action"] = "exclude"
        with self.assertRaisesRegex(ValueError, "excluded_rendered"): self.build()

    def test_replay_preserves_input_and_rejects_claim_tampering(self):
        before = deepcopy((self.source, self.draft, self.bindings, self.scope))
        self.assertEqual(self.build(), self.build())
        self.assertEqual(before, (self.source, self.draft, self.bindings, self.scope))
        for key in ("production_authorized", "full_character_animation"):
            doc = self.build(); doc[key] = True
            with self.assertRaises(ValueError): validate_coverage(doc)
        doc = self.build(); doc["summary"]["source_layers"] += 1
        with self.assertRaises(ValueError): validate_coverage(doc)


if __name__ == "__main__":
    unittest.main()
