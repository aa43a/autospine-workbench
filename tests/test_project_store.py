from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


WORKBENCH_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = WORKBENCH_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from autospine_workbench.project_store import (  # noqa: E402
    AssetNotFoundError,
    ProjectNotFoundError,
    ProjectStore,
    RevisionConflictError,
)


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class StoreFixture:
    def __init__(self, root: Path):
        self.workspace = root / "shared-workspace"
        self.state = root / "private-state"
        self.audit_dir = (
            self.workspace / "tmp" / "psd_audit" / "results" / "fixture-project"
        )
        self.layer_dir = self.audit_dir / "layers"
        self.layer_dir.mkdir(parents=True)
        self.state.mkdir(parents=True)

        self.composite = self.audit_dir / "composite.png"
        self.embedded = self.audit_dir / "embedded_composite.png"
        self.contact_sheet = self.audit_dir / "layers_contact_sheet.png"
        self.layer_image = self.layer_dir / "00_topwear.png"
        for path in (self.composite, self.embedded, self.contact_sheet, self.layer_image):
            path.write_bytes(PNG_SIGNATURE)

        self.audit = {
            "source": str(self.workspace / "fixture.psd"),
            "sha256": "a" * 64,
            "file_size": 1024,
            "canvas": [512, 768],
            "color_mode": "3",
            "depth": 8,
            "channels": 4,
            "top_level_layers": 1,
            "pixel_layers": 1,
            "visible_pixel_layers": 1,
            "empty_pixel_layers": 0,
            "composite_path": str(self.composite),
            "embedded_composite_path": str(self.embedded),
            "layers_contact_sheet_path": str(self.contact_sheet),
            "composite_vs_embedded_mae_rgba": 0.25,
            "composite_vs_embedded_max_abs": 1,
            "layers": [
                {
                    "traversal_index": 0,
                    "depth": 0,
                    "name": "topwear",
                    "kind": "pixel",
                    "is_group": False,
                    "visible": True,
                    "opacity": 255,
                    "blend_mode": "BlendMode.NORMAL",
                    "bbox": [100, 200, 400, 600],
                    "width": 300,
                    "height": 400,
                    "clipping": False,
                    "index": 0,
                    "crop_path": str(self.layer_image),
                    "alpha_nonzero": 50000,
                    "alpha_perceptible": 49000,
                    "alpha_opaque": 45000,
                    "alpha_low_1_7": 1000,
                    "component_count": 1,
                    "component_areas_top5": [49000],
                    "main_component_ratio": 1.0,
                    "empty": False,
                    "fills_bbox_ratio": 0.42,
                }
            ],
        }
        self.audit_path = self.audit_dir / "audit.json"
        self.write_audit()

    def write_audit(self) -> None:
        self.audit_path.write_text(
            json.dumps(self.audit, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def store(self) -> ProjectStore:
        return ProjectStore(self.workspace, state_root=self.state)


class ProjectStoreContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.fixture = StoreFixture(self.root)
        self.store = self.fixture.store()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_project_contract_is_discoverable_and_versioned(self) -> None:
        summaries = self.store.list_projects()
        self.assertEqual([item["id"] for item in summaries], ["fixture-project"])
        project = self.store.get_project("fixture-project")
        self.assertEqual(project["schema_version"], "autospine-workbench.project/v1")
        self.assertEqual(project["canvas"]["coordinate_system"], "canvas-top-left-y-down")
        self.assertEqual(project["overrides"]["revision"], 0)
        self.assertTrue(project["capabilities"]["edit_joints"])
        self.assertFalse(project["capabilities"]["export_spine"])

    def test_revision_conflict_preserves_the_winning_write(self) -> None:
        first = {
            "base_revision": 0,
            "joint_overrides": {},
            "layer_overrides": {},
            "notes": "first reviewer",
        }
        saved = self.store.save_overrides("fixture-project", first)
        self.assertEqual(saved["revision"], 1)
        override_dir = self.fixture.state / "overrides" / "fixture-project"
        history_path = override_dir / "history" / "r000001.json"
        self.assertTrue(history_path.is_file())
        self.assertTrue((override_dir / "latest.json").is_file())

        # History remains authoritative if the replaceable latest cache is lost.
        (override_dir / "latest.json").unlink()

        stale = {
            "base_revision": 0,
            "joint_overrides": {},
            "layer_overrides": {},
            "notes": "stale reviewer",
        }
        with self.assertRaises(RevisionConflictError) as caught:
            self.fixture.store().save_overrides("fixture-project", stale)
        self.assertEqual(caught.exception.requested_revision, 0)
        self.assertEqual(caught.exception.current_revision, 1)

        reloaded = self.fixture.store().get_project("fixture-project")["overrides"]
        self.assertEqual(reloaded["revision"], 1)
        self.assertEqual(reloaded["notes"], "first reviewer")
        self.assertEqual(
            [path.name for path in (override_dir / "history").glob("*.json")],
            ["r000001.json"],
        )

    def test_history_snapshots_are_append_only(self) -> None:
        first = self.store.save_overrides(
            "fixture-project",
            {
                "base_revision": 0,
                "joint_overrides": {},
                "layer_overrides": {},
                "notes": "first",
            },
        )
        override_dir = self.fixture.state / "overrides" / "fixture-project"
        first_path = override_dir / "history" / "r000001.json"
        first_bytes = first_path.read_bytes()

        second = self.store.save_overrides(
            "fixture-project",
            {
                "base_revision": first["revision"],
                "joint_overrides": {},
                "layer_overrides": {},
                "notes": "second",
            },
        )

        self.assertEqual(second["revision"], 2)
        self.assertEqual(first_path.read_bytes(), first_bytes)
        self.assertTrue((override_dir / "history" / "r000002.json").is_file())
        latest = json.loads((override_dir / "latest.json").read_text(encoding="utf-8"))
        self.assertEqual(latest["revision"], 2)
        self.assertEqual(latest["notes"], "second")

    def test_resolved_project_and_validation_apply_reviewed_joint_positions(self) -> None:
        project = self.store.get_project("fixture-project")
        low_confidence = [
            joint for joint in project["skeleton"]["joints"] if joint["confidence"] < 0.5
        ]
        self.assertTrue(low_confidence)
        patch = {
            joint["id"]: {
                "x": joint["x"],
                "y": joint["y"],
                "reason": "reviewed fixture fallback",
            }
            for joint in low_confidence
        }
        self.store.save_overrides(
            "fixture-project",
            {
                "base_revision": 0,
                "joint_overrides": patch,
                "layer_overrides": {},
                "notes": "reviewed all low confidence joints",
            },
        )

        reloaded = self.fixture.store().get_project("fixture-project")
        resolved_joints = {joint["id"]: joint for joint in reloaded["resolved"]["skeleton"]["joints"]}
        for joint in low_confidence:
            effective = resolved_joints[joint["id"]]
            self.assertEqual("manual_adjusted", effective["review_state"])
            self.assertEqual(joint["confidence"], effective["model_confidence"])
        self.assertEqual([], reloaded["resolved"]["qa"]["unresolved_joint_ids"])

        validation = self.fixture.store().validate_project("fixture-project")
        warning_codes = {warning["code"] for warning in validation["warnings"]}
        self.assertNotIn("low_confidence_joints", warning_codes)
        self.assertEqual(1, validation["revision"])

    def test_legacy_override_is_read_and_migrated_without_modification(self) -> None:
        override_root = self.fixture.state / "overrides"
        override_root.mkdir(parents=True)
        legacy_path = override_root / "fixture-project.json"
        legacy_document = {
            "schema_version": "autospine-workbench.override/v1",
            "project_id": "fixture-project",
            "revision": 4,
            "joint_overrides": {},
            "layer_overrides": {},
            "notes": "legacy review",
        }
        legacy_path.write_text(
            json.dumps(legacy_document, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        legacy_bytes = legacy_path.read_bytes()

        loaded = self.fixture.store().get_project("fixture-project")["overrides"]
        self.assertEqual(loaded["revision"], 4)
        self.assertEqual(loaded["notes"], "legacy review")

        saved = self.fixture.store().save_overrides(
            "fixture-project",
            {
                "base_revision": 4,
                "joint_overrides": {},
                "layer_overrides": {},
                "notes": "migrated review",
            },
        )
        project_dir = override_root / "fixture-project"
        self.assertEqual(saved["revision"], 5)
        self.assertEqual(legacy_path.read_bytes(), legacy_bytes)
        self.assertTrue((project_dir / "history" / "r000004.json").is_file())
        self.assertTrue((project_dir / "history" / "r000005.json").is_file())
        latest = json.loads((project_dir / "latest.json").read_text(encoding="utf-8"))
        self.assertEqual(latest["revision"], 5)

    def test_project_id_and_asset_kind_cannot_be_paths(self) -> None:
        with self.assertRaises(ProjectNotFoundError):
            self.store.get_project("../fixture-project")
        with self.assertRaises(ProjectNotFoundError):
            self.store.resolve_asset("..", "composite")
        with self.assertRaises(AssetNotFoundError):
            self.store.resolve_asset("fixture-project", "../../outside")
        with self.assertRaises(AssetNotFoundError):
            self.store.resolve_asset("fixture-project", "layer", "../layer")

    def test_audit_paths_cannot_escape_the_project_directory(self) -> None:
        outside_composite = self.fixture.workspace / "outside.png"
        outside_layer = self.fixture.workspace / "outside-layer.png"
        outside_composite.write_bytes(PNG_SIGNATURE)
        outside_layer.write_bytes(PNG_SIGNATURE)

        self.fixture.audit["composite_path"] = str(outside_composite)
        self.fixture.audit["layers"][0]["crop_path"] = str(outside_layer)
        self.fixture.write_audit()
        store = self.fixture.store()
        project = store.get_project("fixture-project")
        layer_id = project["layers"][0]["id"]

        with self.assertRaises(AssetNotFoundError):
            store.resolve_asset("fixture-project", "composite")
        with self.assertRaises(AssetNotFoundError):
            store.resolve_asset("fixture-project", "layer", layer_id)

    def test_validation_reports_missing_assets_without_exposing_paths(self) -> None:
        self.fixture.layer_image.unlink()
        result = self.store.validate_project("fixture-project")
        self.assertFalse(result["valid"])
        self.assertEqual(result["status"], "invalid")
        self.assertIn("missing_asset", {item["code"] for item in result["errors"]})
        encoded = json.dumps(result)
        self.assertNotIn(str(self.root), encoded)


if __name__ == "__main__":
    unittest.main()
