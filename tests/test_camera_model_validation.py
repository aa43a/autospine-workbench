"""Contract tests for the P8 static orthographic camera model."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.camera_model_validation import (  # noqa: E402
    CameraModelError,
    camera_model_sha256,
    require_camera_matches_kimodo_map,
    require_camera_model,
)
from tests.kimodo_npz_helpers import map_document  # noqa: E402

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover - optional test extra
    Draft202012Validator = None


def camera_document() -> dict:
    return {
        "format": "autospine-camera-model",
        "format_version": 1,
        "camera_id": "kimodo-front-v1",
        "projection": "static_orthographic",
        "basis": {"screen_x": "+X", "screen_y": "-Y", "depth": "+Z"},
        "depth_positive": "away_from_camera",
        "origin": "source_root_frame0",
        "normalization": "map_reference_length",
        "reference_length_meters": 1.0,
    }


class CameraModelValidationTests(unittest.TestCase):
    def test_valid_model_has_deterministic_canonical_hash(self):
        model = camera_document()
        require_camera_model(model)
        reordered = dict(reversed(list(model.items())))
        reordered["basis"] = dict(reversed(list(model["basis"].items())))
        self.assertEqual(
            camera_model_sha256(model), camera_model_sha256(reordered)
        )
        self._schema(model)

    def test_matches_validated_kimodo_map_axes_and_reference(self):
        mapping = map_document()
        model = camera_document()
        require_camera_matches_kimodo_map(model, mapping)

        changed_axis = deepcopy(model)
        changed_axis["basis"] = {
            "screen_x": "+Y", "screen_y": "+X", "depth": "+Z",
        }
        with self.assertRaisesRegex(CameraModelError, "basis differs"):
            require_camera_matches_kimodo_map(changed_axis, mapping)

        changed_reference = deepcopy(model)
        changed_reference["reference_length_meters"] = 2.0
        with self.assertRaisesRegex(CameraModelError, "reference length differs"):
            require_camera_matches_kimodo_map(changed_reference, mapping)

    def test_rejects_extra_fields_nan_bool_and_non_orthogonal_basis(self):
        mutations = (
            lambda value: value.update(extra=True),
            lambda value: value["basis"].update(extra="+X"),
            lambda value: value.update(reference_length_meters=float("nan")),
            lambda value: value.update(reference_length_meters=True),
            lambda value: value["basis"].update(screen_y="-X"),
        )
        for mutate in mutations:
            candidate = camera_document()
            mutate(candidate)
            with self.subTest(candidate=candidate), self.assertRaises(
                CameraModelError
            ):
                require_camera_model(candidate)

    def test_rejects_invalid_literals_and_camera_ids(self):
        mutations = (
            lambda value: value.update(camera_id="../camera"),
            lambda value: value.update(format_version=True),
            lambda value: value.update(projection="perspective"),
            lambda value: value.update(depth_positive="unknown"),
            lambda value: value.update(origin="world_origin"),
            lambda value: value.update(normalization="none"),
            lambda value: value.update(reference_length_meters=0),
            lambda value: value.update(reference_length_meters=1_000_001),
        )
        for mutate in mutations:
            candidate = camera_document()
            mutate(candidate)
            with self.subTest(candidate=candidate), self.assertRaises(
                CameraModelError
            ):
                require_camera_model(candidate)

    def _schema(self, value: dict) -> None:
        if Draft202012Validator is None:
            self.skipTest("jsonschema optional test dependency is unavailable")
        schema = json.loads(
            (ROOT / "schemas" / "camera-model-v1.schema.json").read_text(
                encoding="utf-8"
            )
        )
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(value)


if __name__ == "__main__":
    unittest.main()
