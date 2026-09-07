"""Source-audited 4.3 format and numerical tests; no official Runtime execution."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from tests.test_spine42_json_adapter import rig_fixture, motion_pair, attachment, decode_vertices
from tests.spine42_bundle_helpers import bundle_inputs
from tests.test_region_rig import manifest_fixture, resolved_fixture, LAYER_ID
from autospine_workbench.region_rig import compile_region_rig
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.rig_fk import evaluate_world_setup, local_to_world_point
from autospine_workbench.spine42_json_adapter import build_spine42_json
from autospine_workbench.targets.spine43.contract import (
    Spine43ContractError, canonical_spine43_json, spine43_target_profile,
)
from autospine_workbench.targets.spine43.json_adapter import build_spine43_json, build_spine43_json_bytes
from autospine_workbench.targets.spine43.validation import (
    Spine43ExportValidationError, require_projected_spine43_document, validate_spine43_export,
)


class Spine43AdapterTests(unittest.TestCase):
    def setUp(self):
        self.rig = rig_fixture()

    def test_independent_exact_target_and_explicit_empty_43_constraints(self):
        profile = spine43_target_profile()
        self.assertEqual(profile["skeleton_json_version"], "4.3.26")
        self.assertEqual(profile["runtime"]["version"], "4.3.13")
        self.assertEqual(profile["runtime_verification"], "not_run")
        doc = build_spine43_json(self.rig)
        old = build_spine42_json(self.rig)
        self.assertEqual(doc["skeleton"]["spine"], "4.3.26")
        self.assertEqual(doc["constraints"], [])
        self.assertNotIn("ik", doc)
        self.assertNotEqual(doc["skeleton"]["hash"], old["skeleton"]["hash"])
        self.assertNotEqual(canonical_sha256(doc), canonical_sha256(old))
        self.assertEqual(old["skeleton"]["spine"], "4.2")

    def test_current_reviewed_p2_region_compiles_without_motion(self):
        manifest = manifest_fixture()
        rig = compile_region_rig(
            manifest, resolved_fixture(), layer_manifest_sha256=canonical_sha256(manifest),
            image_sizes={LAYER_ID: [30, 40]},
        ).rig
        doc = build_spine43_json(rig)
        self.assertEqual(doc["animations"], {})
        self.assertEqual(doc["events"], {})
        self.assertEqual(doc["slots"][0]["attachment"], LAYER_ID)
        self.assertEqual(doc["skins"][0]["attachments"][LAYER_ID][LAYER_ID]["type"], "region")

    def test_region_geometry_and_slot_skin_setup_match_audited_43_reader(self):
        doc = build_spine43_json(self.rig)
        self.assertEqual([row["name"] for row in doc["slots"]], ["leg", "face"])
        self.assertEqual(doc["slots"][1]["attachment"], "face-image")
        self.assertNotIn("setupPose", doc["slots"][1])
        self.assertIsInstance(doc["skins"], list)
        region = attachment(doc, "face", "face-image")
        world = evaluate_world_setup(self.rig["bones"])["neck-head"]
        center = local_to_world_point([region["x"], region["y"]],
                                      [world["origin_xy"][0], 400 - world["origin_xy"][1]],
                                      -world["rotation_deg"])
        self.assertAlmostEqual(center[0], 195.0, places=9)
        self.assertAlmostEqual(center[1], 365.0, places=9)
        self.assertAlmostEqual(region["rotation"] - world["rotation_deg"], 0, places=9)

    def test_weighted_mesh_encoding_preserves_each_influence_setup_position(self):
        doc = build_spine43_json(self.rig)
        mesh = attachment(doc, "leg", "leg-mesh")
        self.assertEqual(mesh["triangles"], [0, 1, 2])
        self.assertEqual(mesh["uvs"], [0, 0, 1, 0, 0.5, 1])
        decoded = decode_vertices(mesh["vertices"], 3)
        worlds = evaluate_world_setup(self.rig["bones"])
        for vertex, influences in zip(self.rig["attachments"][1]["vertices"], decoded):
            self.assertAlmostEqual(sum(row[3] for row in influences), 1)
            for bone_index, x, y, _ in influences:
                frame = worlds[doc["bones"][bone_index]["name"]]
                actual = local_to_world_point([x, y], [frame["origin_xy"][0], 400-frame["origin_xy"][1]],
                                              -frame["rotation_deg"])
                self.assertAlmostEqual(actual[0], 120 + vertex[0], places=9)
                self.assertAlmostEqual(actual[1], 400 - 250 - vertex[1], places=9)

    def test_p5_rotation_translation_event_times_use_audited_43_fields(self):
        target, instance = motion_pair(self.rig)
        doc = build_spine43_json(self.rig, target_profile=target, motion_instance=instance)
        animation = doc["animations"][instance["clip_id"]]
        self.assertEqual(animation["bones"]["forearm.left"]["rotate"][1]["value"], 20)
        self.assertEqual(animation["bones"]["upper-arm.left"]["rotate"][1]["value"], -15)
        key = animation["bones"]["root-pelvis"]["translate"][1]
        self.assertEqual((key["x"], key["y"]), (1.5, 2))
        self.assertEqual(len(animation["events"]), 4)
        for row in animation["events"]:
            self.assertIn(row["name"], doc["events"])

    def test_deterministic_bytes_inputs_and_old_42_output_are_unchanged(self):
        before = deepcopy(self.rig)
        old_bytes = canonical_sha256(build_spine42_json(self.rig))
        first = build_spine43_json(self.rig)
        second = build_spine43_json(dict(reversed(list(self.rig.items()))))
        self.assertEqual(first, second)
        self.assertEqual(build_spine43_json_bytes(self.rig), canonical_spine43_json(first))
        self.assertEqual(self.rig, before)
        self.assertEqual(old_bytes, canonical_sha256(build_spine42_json(self.rig)))

    def test_unreviewed_rig_stale_motion_and_new_constraints_fail_closed(self):
        for mutation in ({"qa": {"status": "manual_required"}}, {"constraints": []},
                         {"ik": []}, {"physics": []}, {"sliders": []}):
            with self.subTest(mutation=mutation), self.assertRaises(Spine43ContractError):
                build_spine43_json({**self.rig, **mutation})
        target, instance = motion_pair(self.rig)
        with self.assertRaises(Spine43ContractError):
            build_spine43_json(self.rig, motion_instance=instance)
        target["source"]["p3"]["rig_sha256"] = "f" * 64
        with self.assertRaises(Spine43ContractError):
            build_spine43_json(self.rig, motion_instance=instance, target_profile=target)

    def test_document_validator_rejects_legacy_or_unimplemented_format_fields(self):
        document = build_spine43_json(self.rig)
        variants = []
        for version in ("4.2", "4.3", "4.3.13", "4.3.27"):
            invalid = deepcopy(document)
            invalid["skeleton"]["spine"] = version
            variants.append(invalid)
        variants.extend([{**document, "ik": []}, {**document, "constraints": [{"type": "ik"}]},
                         {**document, "skins": {}}, {**document, "physics": []}])
        invalid = deepcopy(document)
        invalid["slots"][0]["setupPose"] = {"attachment": invalid["slots"][0].pop("attachment")}
        variants.append(invalid)
        invalid = deepcopy(document)
        invalid["slots"][0]["attachment"] = "unknown"
        variants.append(invalid)
        invalid = deepcopy(document)
        invalid["bones"][0]["x"] = float("nan")
        variants.append(invalid)
        invalid = deepcopy(document)
        invalid["bones"][0]["x"] = 10 ** 1000
        variants.append(invalid)
        invalid = deepcopy(document)
        attachment(invalid, "leg", "leg-mesh")["uvs"][0] = True
        variants.append(invalid)
        for invalid in variants:
            with self.subTest(invalid=invalid), self.assertRaises(Spine43ContractError):
                require_projected_spine43_document(invalid)

    def test_export_validator_keeps_actual_43_bytes_and_checks_atlas_png(self):
        data = bundle_inputs()
        document = build_spine43_json(self.rig)
        before = deepcopy(document)
        kwargs = {"expected_skeleton_hash": document["skeleton"]["hash"], "clip_id": None}
        validated = validate_spine43_export(document, data["atlas_bytes"], data["png_bytes"],
                                            data["source_image_sha256s"], **kwargs)
        self.assertEqual(validated.skeleton_json_bytes, canonical_spine43_json(document))
        self.assertEqual(json.loads(validated.skeleton_json_bytes)["skeleton"]["spine"], "4.3.26")
        self.assertEqual(document, before)
        self.assertEqual(validated.attachment_count, 2)
        for key, value in (("png_bytes", b"not-png"), ("atlas_bytes", b"not-atlas"),
                           ("source_image_sha256s", {})):
            corrupt = {**data, key: value}
            with self.subTest(key=key), self.assertRaises(Spine43ExportValidationError):
                validate_spine43_export(document, corrupt["atlas_bytes"], corrupt["png_bytes"],
                                       corrupt["source_image_sha256s"], **kwargs)
        with self.assertRaises(Spine43ExportValidationError):
            validate_spine43_export(build_spine42_json(self.rig), data["atlas_bytes"], data["png_bytes"],
                                   data["source_image_sha256s"], **kwargs)

    def test_mesh_arrays_require_finite_non_boolean_numbers_and_integer_triangles(self):
        document = build_spine43_json(self.rig)
        export = bundle_inputs()
        original = attachment(document, "leg", "leg-mesh")
        mutations = [
            ("uvs", ["bad"] * 6), ("uvs", [True] * 6),
            ("uvs", [float("nan")] * 6), ("uvs", [float("inf")] * 6),
            ("triangles", [0, 1, 2.0]), ("triangles", [0, True, 2]),
            ("triangles", ["0", "1", "2"]), ("triangles", [0, 1, float("nan")]),
        ]
        for key in ("uvs", "vertices", "triangles"):
            mutations.extend((key, value) for value in (None, {}, "012345", tuple(original[key])))
        for bad in ("bad", True, float("nan"), float("inf")):
            vertices = list(original["vertices"])
            vertices[2] = bad
            mutations.append(("vertices", vertices))
        for key, value in mutations:
            with self.subTest(key=key, value=value):
                invalid = deepcopy(document)
                attachment(invalid, "leg", "leg-mesh")[key] = value
                with self.assertRaises(Spine43ContractError):
                    require_projected_spine43_document(invalid)
                with self.assertRaises(Spine43ExportValidationError):
                    validate_spine43_export(
                        invalid, export["atlas_bytes"], export["png_bytes"],
                        export["source_image_sha256s"],
                        expected_skeleton_hash=document["skeleton"]["hash"], clip_id=None,
                    )

    def test_profile_schema_matches_exact_runtime_editor_separation(self):
        try:
            from jsonschema import Draft202012Validator
        except ImportError:
            self.skipTest("jsonschema unavailable")
        schema = json.loads((Path(__file__).resolve().parents[1] /
                             "schemas/spine43-target-profile-v1.schema.json").read_text())
        validator = Draft202012Validator(schema)
        validator.validate(spine43_target_profile())
        invalid = spine43_target_profile()
        invalid["runtime"]["version"] = "4.3.26"
        self.assertTrue(list(validator.iter_errors(invalid)))


if __name__ == "__main__":
    unittest.main()
