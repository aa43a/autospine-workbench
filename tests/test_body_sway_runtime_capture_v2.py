"""RuntimeCapture v2 detached-contract and isolation tests."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for candidate in (ROOT, SRC):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from autospine_workbench.body_sway_runtime_capture_validation import (  # noqa: E402
    BodySwayRuntimeCaptureValidationError,
    require_body_sway_runtime_capture,
)
from autospine_workbench.body_sway_runtime_capture_v2 import (  # noqa: E402
    BodySwayRuntimeCaptureV2,
    BodySwayRuntimeCaptureV2Error,
    require_body_sway_runtime_capture_v2_preview_binding,
)
from autospine_workbench.body_sway_runtime_capture_v2_inventory import (  # noqa: E402
    BodySwayRuntimeCaptureV2InventoryError,
    build_body_sway_runtime_capture_v2_inventory,
)
from autospine_workbench.body_sway_runtime_capture_v2_fields import (  # noqa: E402
    BodySwayRuntimeCaptureV2FieldError,
    require_runtime_v2_world_viewport,
)
from autospine_workbench.body_sway_runtime_capture_v2_validation import (  # noqa: E402
    BodySwayRuntimeCaptureV2ValidationError,
    require_body_sway_runtime_capture_v2,
)
from tests.body_sway_runtime_capture_helpers import capture_png  # noqa: E402
from tests.body_sway_runtime_capture_v2_helpers import (  # noqa: E402
    build_runtime_capture_v2_fixture,
    capture_v2_for_preview,
)
from tests.test_body_sway_preview_inputs_v2 import PreviewV2Fixture  # noqa: E402
from tests.test_temporary_body_sway_preview_v2 import (  # noqa: E402
    _patched_source,
    _source_images,
)
from autospine_workbench.temporary_body_sway_preview_v2 import (  # noqa: E402
    compile_temporary_body_sway_preview_v2,
)

try:  # pragma: no cover - optional dependency
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover
    Draft202012Validator = None


class BodySwayRuntimeCaptureV2Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary, self.fixture = build_runtime_capture_v2_fixture()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_valid_capture_is_copy_isolated_and_deterministic(self) -> None:
        second = BodySwayRuntimeCaptureV2.from_detached(
            self.fixture.document, self.fixture.capture_bytes
        )
        self.assertEqual(self.fixture.capture.canonical_bytes,
                         second.canonical_bytes)
        self.assertEqual(self.fixture.capture.sha256, second.sha256)
        document = self.fixture.capture.document
        captures = self.fixture.capture.capture_bytes
        document.clear()
        captures.clear()
        self.assertTrue(self.fixture.capture.document)
        self.assertTrue(self.fixture.capture.capture_bytes)

    def test_v2_is_not_silently_admitted_by_frozen_v1(self) -> None:
        with self.assertRaises(BodySwayRuntimeCaptureValidationError):
            require_body_sway_runtime_capture(
                self.fixture.document, self.fixture.capture_bytes
            )

    def test_pixel_viewport_and_dpr_are_fixed_but_world_viewport_is_dynamic(self):
        for field, value in (("viewport", {"width": 641, "height": 640}),
                             ("device_pixel_ratio", 2)):
            with self.subTest(field=field):
                document = deepcopy(self.fixture.document)
                document["capture"][field] = value
                with self.assertRaises(BodySwayRuntimeCaptureV2ValidationError):
                    require_body_sway_runtime_capture_v2(
                        document, self.fixture.capture_bytes
                    )

        document = deepcopy(self.fixture.document)
        viewport = {"x": -100.0, "y": -200.0,
                    "width": 1400.0, "height": 1400.0}
        document["capture"]["world_viewport"] = viewport
        document["source"]["world_viewport"] = viewport
        require_body_sway_runtime_capture_v2(
            document, self.fixture.capture_bytes
        )

    def test_source_and_capture_world_viewports_must_match(self) -> None:
        document = deepcopy(self.fixture.document)
        document["source"]["world_viewport"]["x"] += 1
        with self.assertRaises(BodySwayRuntimeCaptureV2ValidationError):
            require_body_sway_runtime_capture_v2(
                document, self.fixture.capture_bytes
            )

    def test_candidate_decision_and_current_head_seals_are_mandatory(self):
        fields = (
            "capture_framing_candidate_sha256",
            "capture_framing_decision_sha256",
            "preview_source_sha256",
        )
        for field in fields:
            with self.subTest(field=field):
                document = deepcopy(self.fixture.document)
                document["source"][field] = "not-a-sha"
                with self.assertRaises(BodySwayRuntimeCaptureV2ValidationError):
                    require_body_sway_runtime_capture_v2(
                        document, self.fixture.capture_bytes
                    )
        document = deepcopy(self.fixture.document)
        document["source"]["capture_framing_revision"] = 0
        with self.assertRaises(BodySwayRuntimeCaptureV2ValidationError):
            require_body_sway_runtime_capture_v2(
                document, self.fixture.capture_bytes
            )

    def test_detached_semantics_explicitly_disclaim_currentness(self) -> None:
        semantics = self.fixture.document["semantics"]
        self.assertFalse(semantics["detached_currentness_claimed"])
        self.assertTrue(
            semantics["currentness_requires_exact_preview_v2_replay"]
        )
        document = deepcopy(self.fixture.document)
        document["semantics"]["detached_currentness_claimed"] = True
        with self.assertRaises(BodySwayRuntimeCaptureV2ValidationError):
            require_body_sway_runtime_capture_v2(
                document, self.fixture.capture_bytes
            )

    def test_payload_is_ready_but_does_not_claim_official_execution(self):
        document = self.fixture.document
        semantics = document["semantics"]
        self.assertTrue(semantics["capture_payload_validated"])
        self.assertTrue(semantics["ready_for_official_runtime_execution"])
        self.assertFalse(semantics["official_runtime_execution_claimed"])
        self.assertFalse(
            semantics["official_runtime_execution_evidence_emitted"]
        )
        self.assertEqual(
            "validated_capture_payload_ready_for_official_runtime_execution",
            document["status"],
        )
        self.assertEqual(
            {"validated-runtime-capture-payload-v2"},
            {row["role"] for row in document["artifacts"]["files"]},
        )
        self.assertNotIn("runtime_session_set_v2_sha256", document["source"])
        changed = deepcopy(document)
        changed["semantics"]["official_runtime_execution_claimed"] = True
        with self.assertRaises(BodySwayRuntimeCaptureV2ValidationError):
            require_body_sway_runtime_capture_v2(
                changed, self.fixture.capture_bytes
            )
        for mutate in (
            lambda row: row.update({"status": "captured_unreviewed"}),
            lambda row: row["artifacts"]["files"][0].update({
                "role": "official-runtime-capture-v2",
            }),
        ):
            changed = deepcopy(document)
            mutate(changed)
            with self.assertRaises(BodySwayRuntimeCaptureV2ValidationError):
                require_body_sway_runtime_capture_v2(
                    changed, self.fixture.capture_bytes
                )

    def test_world_viewport_accepts_contract_boundary_and_rejects_overflow(self):
        boundary = {
            "x": 1e12, "y": -1e12,
            "width": 1e12, "height": 1e12,
        }
        self.assertEqual(boundary, require_runtime_v2_world_viewport(boundary))
        for value in (
            {**boundary, "x": 1e12 + 1},
            {**boundary, "y": -(1e12 + 1)},
            {**boundary, "width": 1e12 + 1, "height": 1e12 + 1},
        ):
            with self.subTest(value=value):
                with self.assertRaises(BodySwayRuntimeCaptureV2FieldError):
                    require_runtime_v2_world_viewport(value)

    def test_case_stream_and_png_bytes_are_exact(self) -> None:
        document = deepcopy(self.fixture.document)
        document["cases"][0]["png_sha256"] = "0" * 64
        with self.assertRaises(BodySwayRuntimeCaptureV2ValidationError):
            require_body_sway_runtime_capture_v2(
                document, self.fixture.capture_bytes
            )
        captures = dict(self.fixture.capture_bytes)
        first = next(iter(captures))
        captures[first] = captures[first][:-1] + b"\x00"
        with self.assertRaises((
            BodySwayRuntimeCaptureV2ValidationError,
            BodySwayRuntimeCaptureV2InventoryError,
        )):
            require_body_sway_runtime_capture_v2(self.fixture.document, captures)

    def test_png_dimensions_are_exactly_640_square(self) -> None:
        captures = {"captures/setup.png": capture_png(639, 640)}
        with self.assertRaises(BodySwayRuntimeCaptureV2InventoryError):
            build_body_sway_runtime_capture_v2_inventory(
                ["setup", "base", "combined"], captures
            )

    def test_from_detached_rejects_invalid_contract(self) -> None:
        document = deepcopy(self.fixture.document)
        document["format_version"] = 1
        with self.assertRaises(BodySwayRuntimeCaptureV2Error):
            BodySwayRuntimeCaptureV2.from_detached(
                document, self.fixture.capture_bytes
            )

    @unittest.skipIf(Draft202012Validator is None, "jsonschema is optional")
    def test_public_document_matches_schema(self) -> None:
        schema = json.loads((
            ROOT / "schemas" / "body-sway-runtime-capture-v2.schema.json"
        ).read_text("utf-8"))
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(self.fixture.document)


class BodySwayRuntimeCaptureV2PreviewBindingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary, cls.template = build_runtime_capture_v2_fixture()
        cls.preview_fixture = PreviewV2Fixture(
            Path(cls.temporary.name) / "preview-v2"
        )
        inputs = cls.preview_fixture.admit()
        images = _source_images(cls.preview_fixture.fixture.mesh.rig)
        with _patched_source(images):
            cls.preview = compile_temporary_body_sway_preview_v2(
                inputs, cls.preview_fixture.fixture.mesh,
            )
        cls.capture = capture_v2_for_preview(cls.preview, cls.template)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def test_exact_preview_binding_accepts_all_three_framing_surfaces(self):
        require_body_sway_runtime_capture_v2_preview_binding(
            self.capture, self.preview
        )

    def test_detached_valid_candidate_change_fails_exact_preview_replay(self):
        document = self.capture.document
        document["source"]["capture_framing_candidate_sha256"] = "0" * 64
        changed = BodySwayRuntimeCaptureV2.from_detached(
            document, self.capture.capture_bytes
        )
        with self.assertRaises(BodySwayRuntimeCaptureV2Error):
            require_body_sway_runtime_capture_v2_preview_binding(
                changed, self.preview
            )


if __name__ == "__main__":
    unittest.main()
