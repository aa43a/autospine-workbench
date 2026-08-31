"""Public capture-framed TemporaryBodySwayPreview v2 contract tests."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest.mock import patch

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover - optional test dependency
    Draft202012Validator = None


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for candidate in (ROOT, SRC):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from autospine_workbench.png_rgba import RgbaImage, encode_rgba_png  # noqa: E402
from autospine_workbench.temporary_body_sway_preview_v2 import (  # noqa: E402
    TemporaryBodySwayPreviewV2,
    TemporaryBodySwayPreviewV2Error,
    compile_temporary_body_sway_preview_v2,
    require_exact_temporary_body_sway_preview_v2,
)
from autospine_workbench.temporary_body_sway_preview_validation import (  # noqa: E402
    TemporaryBodySwayPreviewValidationError,
    require_temporary_body_sway_preview,
)
from autospine_workbench.temporary_body_sway_preview_validation_v2 import (  # noqa: E402
    TemporaryBodySwayPreviewValidationV2Error,
    require_temporary_body_sway_preview_manifest_v2,
    require_temporary_body_sway_preview_v2,
    temporary_body_sway_preview_sha256_v2,
)
from tests.test_body_sway_preview_inputs_v2 import PreviewV2Fixture  # noqa: E402


class TemporaryBodySwayPreviewV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.fixture = PreviewV2Fixture(Path(cls.temporary.name))
        cls.inputs = cls.fixture.admit()
        cls.images = _source_images(cls.fixture.fixture.mesh.rig)
        with _patched_source(cls.images):
            cls.value = compile_temporary_body_sway_preview_v2(
                cls.inputs, cls.fixture.fixture.mesh,
            )

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_is_deterministic_valid_frozen_and_v1_is_still_frozen(self):
        with _patched_source(self.images):
            second = compile_temporary_body_sway_preview_v2(
                self.inputs, self.fixture.fixture.mesh,
            )
        self.assertIs(type(self.value), TemporaryBodySwayPreviewV2)
        self.assertEqual(self.value, second)
        require_temporary_body_sway_preview_manifest_v2(self.value.document)
        require_temporary_body_sway_preview_v2(
            self.value.document, self.value.artifact_bytes,
        )
        self.assertEqual(
            self.value.sha256,
            temporary_body_sway_preview_sha256_v2(
                self.value.document, self.value.artifact_bytes,
            ),
        )
        with self.assertRaises(TemporaryBodySwayPreviewValidationError):
            require_temporary_body_sway_preview(
                self.value.document, self.value.artifact_bytes,
            )

    @unittest.skipIf(Draft202012Validator is None, "jsonschema is optional")
    def test_public_document_matches_the_v2_schema(self):
        import json
        schema = json.loads((
            ROOT / "schemas" / "temporary-body-sway-preview-v2.schema.json"
        ).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(self.value.document)

    def test_framing_identity_is_cross_bound_in_all_runtime_surfaces(self):
        document = self.value.document
        source, projection = document["source"], document["projection"]
        plan = document["capture_plan"]
        session = _json(self.value.artifact_bytes["runtime/session.json"])
        skeleton = _json(self.value.artifact_bytes["runtime/skeleton.json"])
        self.assertEqual(self.inputs.world_viewport, projection["world_viewport"])
        self.assertEqual(self.inputs.world_viewport, plan["world_viewport"])
        self.assertEqual(self.inputs.world_viewport, {
            field: skeleton["skeleton"][field]
            for field in ("x", "y", "width", "height")
        })
        for field in (
            "capture_framing_candidate_sha256",
            "capture_framing_decision_sha256", "capture_framing_revision",
        ):
            self.assertEqual(source[field], projection[field])
            self.assertEqual(source[field], plan["source"][field])
            self.assertEqual(source[field], session["source"][field])
        self.assertEqual({"width": 640, "height": 640}, plan["viewport"])
        self.assertEqual(1, plan["device_pixel_ratio"])
        self.assertEqual(
            self.inputs.framing_candidate["source"]["current_p10_1_head"],
            source["current_p10_1_head"],
        )

    def test_exact_replay_and_each_framing_tamper_fail_closed(self):
        with _patched_source(self.images):
            self.assertEqual(
                self.value.sha256,
                require_exact_temporary_body_sway_preview_v2(
                    self.inputs, self.fixture.fixture.mesh,
                    self.value.document, self.value.artifact_bytes,
                ),
            )
        for mutate in (
            lambda row: row["source"].update({
                "capture_framing_revision": row["source"]
                ["capture_framing_revision"] + 1,
            }),
            lambda row: row["projection"]["world_viewport"].update({
                "x": row["projection"]["world_viewport"]["x"] + 1,
            }),
            lambda row: row["capture_plan"]["world_viewport"].update({
                "y": row["capture_plan"]["world_viewport"]["y"] + 1,
            }),
        ):
            changed = deepcopy(self.value.document)
            mutate(changed)
            with self.assertRaises(TemporaryBodySwayPreviewValidationV2Error):
                require_temporary_body_sway_preview_v2(
                    changed, self.value.artifact_bytes,
                )
        changed = self.value.artifact_bytes
        changed["runtime/skeleton.json"] += b" "
        with self.assertRaises(TemporaryBodySwayPreviewValidationV2Error):
            require_temporary_body_sway_preview_v2(self.value.document, changed)

    def test_replay_rejects_a_different_exact_package(self):
        changed = deepcopy(self.value.document)
        changed["status"] = "ready_for_official_runtime_capture"
        with _patched_source(self.images), self.assertRaises(
            TemporaryBodySwayPreviewV2Error,
        ):
            require_exact_temporary_body_sway_preview_v2(
                self.inputs, self.fixture.fixture.mesh,
                changed, self.value.artifact_bytes,
            )


def _source_images(rig):
    result = {}
    for index, attachment in enumerate(rig["attachments"]):
        width, height = attachment["size"]
        pixel = bytes((30 + index, 80, 120, 255))
        result[attachment["id"]] = encode_rgba_png(
            RgbaImage(width, height, pixel * (width * height))
        )
    return result


def _patched_source(images):
    return patch(
        "autospine_workbench.temporary_body_sway_preview_artifacts_v2."
        "verified_mesh_source_from_bundle",
        return_value=SimpleNamespace(png_by_attachment=images),
    )


def _json(raw):
    import json
    return json.loads(raw.decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
