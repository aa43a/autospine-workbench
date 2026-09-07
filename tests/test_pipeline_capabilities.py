"""Operation capability gates and immutable current-input observations."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests.test_layer_manifest import project_fixture, write_png
from tests.resolved_snapshot_helpers import refresh_resolved_snapshot
from autospine_workbench.automation.capability_resolver import (
    CapabilityError, resolve_capabilities, validate_project_capabilities,
)
from autospine_workbench.automation.project_snapshot import observe_project, SnapshotError
from autospine_workbench.current_project_chain import rebuild_current_project_chains


class PipelineCapabilitiesTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.asset = self.directory / "arm.png"
        write_png(self.asset, 30, 40)
        self.project = project_fixture()
        layer = self.project["resolved"]["layers"][0]
        layer["candidate_bone"] = "root-tip"
        layer["reviewed_fields"].append("candidate_bone")
        self.project["resolved"] = refresh_resolved_snapshot(self.project["resolved"])
        owner = self

        class Store:
            def get_project(self, project_id):
                return deepcopy(owner.project)

            def resolve_asset(self, project_id, kind, layer_id):
                return owner.asset

        self.store = Store()

    def test_ready_setup_can_preview_but_never_mesh_motion_or_release(self):
        with observe_project(self.store, "sample-a") as snapshot:
            capabilities = resolve_capabilities(snapshot)
            self.assertTrue(capabilities["can_build_spine_preview"])
            self.assertTrue(capabilities["can_build_region_rig"])
            self.assertFalse(capabilities["can_build_mesh_rig"])
            self.assertFalse(capabilities["can_apply_motion"])
            self.assertFalse(capabilities["can_export_spine"])
            self.assertEqual(snapshot.region_compilation.rig["qa"]["status"], "passed")
            self.assertEqual(snapshot.assets["layers/layer-001-arm-l.png"], self.asset)
            self.assertEqual(snapshot.materialized_assets["layer-001-arm-l"], self.asset)
        self.assertEqual(list(self.directory.iterdir()), [self.asset])

    def test_exact_historical_chain_addresses_unchanged(self):
        old = rebuild_current_project_chains(self.store, ["sample-a"])["sample-a"]
        with observe_project(self.store, "sample-a") as snapshot:
            self.assertEqual(snapshot.source_addresses["layer_manifest_sha256"], old.layer_manifest_sha256)
            self.assertEqual(snapshot.source_addresses["input_identity_sha256"], old.input_identity_sha256)

    def test_reviewed_region_gate_does_not_upgrade_draft_to_spine(self):
        layer = self.project["resolved"]["layers"][0]
        layer["reviewed_fields"].remove("pivot_xy")
        self.project["resolved"] = refresh_resolved_snapshot(self.project["resolved"])
        with observe_project(self.store, "sample-a") as snapshot:
            draft = resolve_capabilities(snapshot, "draft_auto")
            production = resolve_capabilities(snapshot)
            self.assertTrue(draft["can_build_region_rig"])
            self.assertFalse(draft["can_build_spine_preview"])
            self.assertFalse(production["can_build_region_rig"])
            self.assertIn("project_review_required", [v["reason_code"] for v in draft["warning_items"]])

    def test_certification_keeps_exact_entry_separate(self):
        with observe_project(self.store, "sample-a") as snapshot:
            document = resolve_capabilities(snapshot, "certification_exact")
            self.assertFalse(document["can_build_region_rig"])
            self.assertEqual(document["blocking_items"][0]["reason_code"], "certification_exact_entry_required")

    def test_source_drift_after_yield_is_rejected(self):
        with self.assertRaises(SnapshotError) as caught:
            with observe_project(self.store, "sample-a"):
                write_png(self.asset, 31, 40)
        self.assertEqual(caught.exception.reason_code, "project_changed_during_snapshot")

    def test_authoring_drift_after_yield_is_rejected(self):
        with self.assertRaises(SnapshotError) as caught:
            with observe_project(self.store, "sample-a"):
                self.project["resolved"]["layers"][0]["notes"] = "changed"
                self.project["resolved"] = refresh_resolved_snapshot(self.project["resolved"])
        self.assertEqual(caught.exception.reason_code, "project_changed_during_snapshot")

    def test_authoring_drift_during_manifest_build_is_rejected_before_yield(self):
        from autospine_workbench.layer_manifest import LayerManifestBuilder
        original = LayerManifestBuilder.build

        def drifting_build(builder, *args, **kwargs):
            result = original(builder, *args, **kwargs)
            self.project["resolved"]["layers"][0]["notes"] = "concurrent edit"
            self.project["resolved"] = refresh_resolved_snapshot(self.project["resolved"])
            return result

        with patch.object(LayerManifestBuilder, "build", drifting_build):
            with self.assertRaises(SnapshotError) as caught:
                with observe_project(self.store, "sample-a"):
                    self.fail("concurrent mutation was yielded")
        self.assertEqual(caught.exception.reason_code, "project_changed_during_snapshot")

    def test_split_assets_survive_only_for_context_lifetime(self):
        from tests.test_layer_split_materializer import project_fixture, source_image
        from autospine_workbench.png_rgba import write_rgba_png
        self.project = project_fixture()
        write_rgba_png(self.asset, source_image())
        original_bytes = self.asset.read_bytes()
        with observe_project(self.store, "sample-split") as snapshot:
            children = [path for key, path in snapshot.materialized_assets.items() if "--" in key]
            self.assertEqual(len(children), 2)
            self.assertTrue(all(path.is_file() for path in children))
            self.assertTrue(all(path in snapshot.assets.values() for path in children))
        self.assertTrue(all(not path.exists() for path in children))
        self.assertEqual(self.asset.read_bytes(), original_bytes)

    def test_missing_project_and_asset_have_sanitized_reason_codes(self):
        from autospine_workbench.project_store import ProjectNotFoundError, AssetNotFoundError
        with patch.object(self.store, "get_project", side_effect=ProjectNotFoundError("private/path")):
            with self.assertRaises(SnapshotError) as caught:
                with observe_project(self.store, "sample-a"):
                    self.fail("missing project yielded")
        self.assertEqual(str(caught.exception), "project_not_found")
        with patch.object(self.store, "resolve_asset", side_effect=AssetNotFoundError("private/path", "asset")):
            with self.assertRaises(SnapshotError) as caught:
                with observe_project(self.store, "sample-a"):
                    self.fail("missing asset yielded")
        self.assertEqual(str(caught.exception), "project_asset_unavailable")

    def test_nonfinite_input_is_blocked_without_path_leak(self):
        self.project["resolved"]["layers"][0]["opacity"] = float("nan")
        with self.assertRaises(SnapshotError) as caught:
            with observe_project(self.store, "sample-a"):
                self.fail("invalid input was yielded")
        self.assertEqual(str(caught.exception), "project_snapshot_invalid")

    def test_non_normal_blend_is_not_advertised(self):
        self.project["resolved"]["layers"][0]["blend_mode"] = "multiply"
        self.project["resolved"] = refresh_resolved_snapshot(self.project["resolved"])
        with observe_project(self.store, "sample-a") as snapshot:
            self.assertIsNone(snapshot.region_compilation)
            result = resolve_capabilities(snapshot)
            self.assertFalse(result["can_build_spine_preview"])
            self.assertEqual(result["blocking_items"][0]["reason_code"], "region_geometry_unsupported")

    def test_schema_and_validator_reject_same_structural_mutations(self):
        try:
            from jsonschema import Draft202012Validator
        except ImportError:
            self.skipTest("jsonschema unavailable")
        path = Path(__file__).resolve().parents[1] / "schemas/project-capabilities-v1.schema.json"
        validator = Draft202012Validator(json.loads(path.read_text(encoding="utf-8")))
        with observe_project(self.store, "sample-a") as snapshot:
            valid = resolve_capabilities(snapshot)
        validator.validate(valid)
        mutations = [
            {"can_build_mesh_rig": True}, {"can_apply_motion": True},
            {"can_export_spine": True}, {"authority": "release"},
            {"can_build_region_rig": False}, {"profile": "certification_exact"},
            {"project_id": "C:/private/project"}, {"can_build_region_rig": 1},
            {"source_addresses": {}}, {"state_root": "C:/private"},
            {"blocking_items": [{"type": "review", "id": "project", "reason_code": "project_review_required"}]},
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                invalid = {**valid, **mutation}
                self.assertTrue(list(validator.iter_errors(invalid)))
                with self.assertRaises(CapabilityError):
                    validate_project_capabilities(invalid)


if __name__ == "__main__":
    unittest.main()
