from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.override_store import OverrideHistoryStore  # noqa: E402
from tests.test_split_specs import (  # noqa: E402
    JOINTS,
    normalize_patch,
    valid_patch,
)

try:
    from jsonschema import Draft202012Validator
    from jsonschema.exceptions import ValidationError
except ImportError:  # pragma: no cover - dependency-free runtime
    Draft202012Validator = None
    ValidationError = Exception


class SplitSpecMigrationAndPersistenceTests(unittest.TestCase):
    def test_v1_v2_migration_preserves_legacy_review_fields(self) -> None:
        for version in (
            "autospine-workbench.override/v1",
            "autospine-workbench.override/v2",
        ):
            with self.subTest(version=version):
                patch = valid_patch(version=version)
                patch["joint_overrides"] = {
                    "wrist.left": {
                        "x": 12,
                        "y": 34,
                        "confidence": 0.75,
                        "reason": "reviewed",
                    }
                }
                patch["layer_overrides"]["layer-footwear"] = {
                    "canonical_role": "body.foot",
                    "side": "bilateral",
                    "disposition": "review",
                    "visible": False,
                    "pivot_xy": [20, 30],
                    "candidate_bone": "calf.left",
                    "notes": "legacy fields",
                }
                if version.endswith("/v2"):
                    patch["joint_decisions"] = {
                        "ankle.left": {
                            "action": "unobservable",
                            "candidate_artifact_sha256": "a" * 64,
                            "reason": "hidden by the costume",
                        }
                    }

                normalized = normalize_patch(patch)

                self.assertEqual(
                    {
                        "x": 12.0,
                        "y": 34.0,
                        "confidence": 0.75,
                        "reason": "reviewed",
                    },
                    normalized["joint_overrides"]["wrist.left"],
                )
                for field, value in patch["layer_overrides"]["layer-footwear"].items():
                    self.assertEqual(
                        [20.0, 30.0] if field == "pivot_xy" else value,
                        normalized["layer_overrides"]["layer-footwear"][field],
                    )
                self.assertEqual(
                    patch["joint_decisions"], normalized["joint_decisions"]
                )
                self.assertEqual(patch["notes"], normalized["notes"])

    def test_v3_split_spec_survives_save_history_and_reload(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state_root = Path(directory)
            store = OverrideHistoryStore(state_root)
            arguments = {
                "joint_ids": JOINTS,
                "layer_ids": {"layer-footwear"},
                "canvas_width": 100,
                "canvas_height": 200,
            }

            patch = valid_patch()
            patch["base_revision"] = 0
            saved = store.save("sample", patch, **arguments)
            reloaded = OverrideHistoryStore(state_root).load(
                "sample", **arguments
            )
            history_path = (
                state_root
                / "overrides"
                / "sample"
                / "history"
                / "r000001.json"
            )
            persisted = json.loads(history_path.read_text(encoding="utf-8"))

            expected = saved["layer_overrides"]["layer-footwear"]["split_spec"]
            self.assertEqual(expected, persisted["layer_overrides"]["layer-footwear"]["split_spec"])
            self.assertEqual(expected, reloaded["layer_overrides"]["layer-footwear"]["split_spec"])
            self.assertEqual(saved, reloaded)


@unittest.skipIf(Draft202012Validator is None, "install the test extra for schema checks")
class SplitSpecSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with (ROOT / "schemas" / "override-patch-v3.schema.json").open(
            "r", encoding="utf-8"
        ) as stream:
            cls.schema = json.load(stream)
        Draft202012Validator.check_schema(cls.schema)
        cls.validator = Draft202012Validator(cls.schema)

    def test_v3_patch_validates(self) -> None:
        self.validator.validate(valid_patch())

    def test_schema_rejects_parent_rig_fields_and_open_anchor_shapes(self) -> None:
        parent_field = valid_patch()
        parent_field["layer_overrides"]["layer-footwear"]["pivot_xy"] = [1, 2]
        with self.assertRaises(ValidationError):
            self.validator.validate(parent_field)

        open_anchor = valid_patch()
        open_anchor["layer_overrides"]["layer-footwear"]["split_spec"]["parts"]["left"][
            "pivot"
        ]["extra"] = True
        with self.assertRaises(ValidationError):
            self.validator.validate(open_anchor)

    def test_schema_requires_side_specific_proxy_and_limb_bone_ids(self) -> None:
        missing_id = valid_patch()
        del missing_id["layer_overrides"]["layer-footwear"]["split_spec"]["parts"][
            "left"
        ]["guide"][2]["proxy_id"]
        with self.assertRaises(ValidationError):
            self.validator.validate(missing_id)

        wrong_side = valid_patch()
        left = wrong_side["layer_overrides"]["layer-footwear"]["split_spec"]["parts"][
            "left"
        ]
        left["guide"][2]["proxy_id"] = "shoe-opening.right"
        with self.assertRaises(ValidationError):
            self.validator.validate(wrong_side)

        valid_proxy_for = valid_patch()
        proxy = valid_proxy_for["layer_overrides"]["layer-footwear"]["split_spec"][
            "parts"
        ]["left"]["guide"][2]
        proxy["proxy_for_joint_id"] = "ankle.left"
        self.validator.validate(valid_proxy_for)
        proxy["proxy_for_joint_id"] = "ankle.right"
        with self.assertRaises(ValidationError):
            self.validator.validate(valid_proxy_for)

        center_bone = valid_patch()
        center_bone["layer_overrides"]["layer-footwear"]["split_spec"]["parts"][
            "left"
        ]["candidate_bone"] = "pelvis-spine"
        with self.assertRaises(ValidationError):
            self.validator.validate(center_bone)


if __name__ == "__main__":
    unittest.main()
