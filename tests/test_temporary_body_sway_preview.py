"""Public TemporaryBodySwayPreview v1 compiler and byte-contract tests."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import sys
import tempfile
import unittest

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover - optional test dependency
    Draft202012Validator = None


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.body_sway_preview_profile import (  # noqa: E402
    PREVIEW_RELEASE_GATE,
)
from autospine_workbench.temporary_body_sway_preview import (  # noqa: E402
    TemporaryBodySwayPreviewError,
    compile_temporary_body_sway_preview,
    require_exact_temporary_body_sway_preview,
)
from autospine_workbench.temporary_body_sway_preview_validation import (  # noqa: E402
    TemporaryBodySwayPreviewValidationError,
    require_temporary_body_sway_preview,
    require_temporary_body_sway_preview_manifest,
    temporary_body_sway_preview_sha256,
)
from tests.body_sway_preview_helpers import BodySwayPreviewFixture  # noqa: E402
from tests.p9_v2_helpers import tree  # noqa: E402


class TemporaryBodySwayPreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.fixture = BodySwayPreviewFixture(Path(cls.temporary.name))
        cls.before = tree(cls.fixture.persisted.state)
        cls.value = compile_temporary_body_sway_preview(
            cls.fixture.preview_inputs, cls.fixture.chain.mesh_bundle
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def test_is_deterministic_valid_frozen_copy_isolated_and_zero_write(self):
        second = compile_temporary_body_sway_preview(
            self.fixture.preview_inputs, self.fixture.chain.mesh_bundle
        )
        self.assertEqual(self.value, second)
        self.assertEqual(self.before, tree(self.fixture.persisted.state))
        require_temporary_body_sway_preview_manifest(self.value.document)
        require_temporary_body_sway_preview(
            self.value.document, self.value.artifact_bytes
        )
        self.assertEqual(
            self.value.sha256,
            temporary_body_sway_preview_sha256(
                self.value.document, self.value.artifact_bytes
            ),
        )
        changed = self.value.document
        changed["summary"].clear()
        self.assertTrue(self.value.document["summary"])
        with self.assertRaises(FrozenInstanceError):
            self.value._canonical_json = "{}"  # type: ignore[misc]

    def test_source_binds_complete_probe_candidate_decision_and_stage_chain(self):
        source = self.value.document["source"]
        report = self.fixture.report.document
        self.assertEqual(self.fixture.report.sha256,
                         source["body_sway_probe_report_sha256"])
        for field in (
            "idle_behavior_candidates_sha256",
            "idle_behavior_decision_sha256", "layer_manifest_sha256",
            "p3", "p5", "p9",
        ):
            self.assertEqual(report["source"][field], source[field])

    def test_trusted_upstream_replay_requires_byte_identical_package(self):
        self.assertEqual(
            self.value.sha256,
            require_exact_temporary_body_sway_preview(
                self.fixture.preview_inputs,
                self.fixture.chain.mesh_bundle,
                self.value.document,
                self.value.artifact_bytes,
            ),
        )
        changed = self.value.document
        changed["project_id"] += "-forged"
        with self.assertRaises(TemporaryBodySwayPreviewError):
            require_exact_temporary_body_sway_preview(
                self.fixture.preview_inputs,
                self.fixture.chain.mesh_bundle,
                changed,
                self.value.artifact_bytes,
            )

    def test_semantics_truthfully_emit_only_an_ephemeral_runtime_timeline(self):
        document = self.value.document
        semantics = document["semantics"]
        self.assertTrue(semantics["runtime_timeline_emitted"])
        for field in (
            "motion_instance_v3_emitted", "publishable", "release_authority",
            "safe_range_claimed", "continuous_time_safety_claimed",
            "visual_quality_claimed", "raster_truth_claimed",
            "official_runtime_execution_claimed", "human_review_claimed",
        ):
            self.assertFalse(semantics[field])
        self.assertEqual(PREVIEW_RELEASE_GATE, document["release_gate"])
        self.assertTrue(semantics["content_digests_are_compiler_seals"])
        self.assertTrue(semantics["upstream_replay_requires_exact_inputs"])
        self.assertFalse(semantics["standalone_upstream_authenticity_claimed"])
        self.assertEqual(
            "structure-and-internal-consistency",
            semantics["detached_validation_scope"],
        )
        self.assertEqual("ready_for_official_runtime_capture",
                         document["status"])

    @unittest.skipIf(Draft202012Validator is None, "jsonschema is optional")
    def test_compiler_output_matches_the_published_json_schema(self):
        schema = json.loads((
            ROOT / "schemas" / "temporary-body-sway-preview-v1.schema.json"
        ).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(self.value.document)

    def test_each_missing_extra_or_tampered_artifact_byte_is_rejected(self):
        paths = tuple(self.value.artifact_bytes)
        for path in paths:
            with self.subTest(path=path):
                missing = self.value.artifact_bytes
                missing.pop(path)
                with self.assertRaises(TemporaryBodySwayPreviewValidationError):
                    require_temporary_body_sway_preview(
                        self.value.document, missing
                    )
                damaged = self.value.artifact_bytes
                damaged[path] += b"x"
                with self.assertRaises(TemporaryBodySwayPreviewValidationError):
                    require_temporary_body_sway_preview(
                        self.value.document, damaged
                    )
        extra = self.value.artifact_bytes
        extra["runtime/extra.txt"] = b"x"
        with self.assertRaises(TemporaryBodySwayPreviewValidationError):
            require_temporary_body_sway_preview(self.value.document, extra)

    def test_projection_summary_or_release_claim_tamper_is_rejected(self):
        for mutate in (
            lambda value: value["projection"].update({
                "rotation_key_count": value["projection"]["rotation_key_count"] + 1
            }),
            lambda value: value["summary"].update({"bone_count": 999}),
            lambda value: value["semantics"].update({"publishable": True}),
            lambda value: value.update({"release_gate": {
                "status": "passed", "reason_codes": []
            }}),
        ):
            document = deepcopy(self.value.document)
            mutate(document)
            with self.assertRaises(TemporaryBodySwayPreviewValidationError):
                require_temporary_body_sway_preview(
                    document, self.value.artifact_bytes
                )


if __name__ == "__main__":
    unittest.main()
