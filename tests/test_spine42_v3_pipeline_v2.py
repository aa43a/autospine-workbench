"""Exact historical P10.6b v2 to P10.7a v2 pipeline tests."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
for item in (ROOT, ROOT / "src"):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from autospine_workbench.spine42_v3_pipeline_result_v2 import (  # noqa: E402
    VerifiedSpine42V3CompilationV2,
)
from autospine_workbench.spine42_v3_pipeline_v2 import (  # noqa: E402
    VerifiedSpine42V3PipelineV2, VerifiedSpine42V3PipelineV2Error,
)
from tests.spine42_v3_v2_helpers import Spine42V3V2Fixture  # noqa: E402


def _tree(root):
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in Path(root).rglob("*") if path.is_file()
    }


class Spine42V3PipelineV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.fixture = Spine42V3V2Fixture(Path(cls.temporary.name))
        cls.pipeline = VerifiedSpine42V3PipelineV2(cls.fixture.state_root)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def build(self):
        fixture = self.fixture
        with fixture.pipeline_sources() as mocks:
            result = self.pipeline.build(
                fixture.motion_bundle.project_id,
                fixture.motion_bundle.motion_instance_v3_sha256,
                fixture.motion_bundle.bundle_sha256,
            )
        return result, mocks

    def test_exact_read_build_is_pure_and_v2_bound(self):
        before = _tree(self.fixture.state_root)
        result, mocks = self.build()
        self.assertEqual(before, _tree(self.fixture.state_root))
        self.assertIs(type(result), VerifiedSpine42V3CompilationV2)
        self.assertEqual(
            self.fixture.motion_bundle.motion_instance_v3_sha256,
            result.motion_instance_v3_sha256,
        )
        self.assertEqual(
            self.fixture.motion_bundle.bundle_sha256,
            result.motion_instance_v3_bundle_sha256,
        )
        self.assertEqual(2, result.run_manifest["format_version"])
        self.assertEqual(
            ("skeleton.json", "skeleton.atlas", "skeleton.png",
             "run-manifest.json", "export-report.json"),
            result.inventory,
        )
        mocks["MotionInstanceV3BundleReaderV2.load"].assert_called_once_with(
            self.fixture.motion_bundle.project_id,
            self.fixture.motion_bundle.motion_instance_v3_sha256,
            self.fixture.motion_bundle.bundle_sha256,
        )
        mocks["VerifiedReviewedMotionBundleReader.load"].assert_called_once_with(
            self.fixture.motion_bundle.project_id,
            self.fixture.reviewed.motion_instance_v2_sha256,
            self.fixture.reviewed.bundle_sha256,
        )

    def test_historical_rebuild_is_deterministic_and_never_observes_heads(self):
        expected, _mocks = self.build()
        with patch(
            "autospine_workbench.spine42_v3_current_heads_v2."
            "observe_spine42_v3_current_heads_v2",
            side_effect=AssertionError("current head observed"),
        ), patch(
            "autospine_workbench.body_sway_dynamic_seam_head_checks_v2."
            "require_current_body_sway_dynamic_seam_heads_v2",
            side_effect=AssertionError("dynamic head observed"),
        ), self.fixture.pipeline_sources():
            rebuilt = self.pipeline.rebuild_and_verify(expected)
        self.assertEqual(expected, rebuilt)

    def test_already_verified_entry_does_not_read_p10_6b_again(self):
        with self.fixture.pipeline_sources() as mocks:
            mocks["MotionInstanceV3BundleReaderV2"].side_effect = \
                AssertionError("P10.6b reread")
            result = self.pipeline.build_from_verified(
                self.fixture.motion_bundle
            )
        mocks["MotionInstanceV3BundleReaderV2"].assert_not_called()
        self.assertEqual(
            self.fixture.motion_bundle.bundle_sha256,
            result.motion_instance_v3_bundle_sha256,
        )

    def test_already_verified_entry_rejects_pseudo_source(self):
        with self.assertRaisesRegex(
            VerifiedSpine42V3PipelineV2Error, "reader-issued",
        ):
            self.pipeline.build_from_verified(object())

    def test_already_verified_entry_rejects_cross_address(self):
        bundle_type = type(self.fixture.motion_bundle)
        original = bundle_type.document

        def attacked(bundle, name):
            value = deepcopy(original(bundle, name))
            if name == "run-manifest-v2.json":
                value["inputs"]["p9"]["bundle_sha256"] = "f" * 64
            return value

        with self.fixture.pipeline_sources(), patch.object(
            bundle_type, "document", attacked,
        ), self.assertRaisesRegex(
            VerifiedSpine42V3PipelineV2Error, "source chain",
        ):
            self.pipeline.build_from_verified(self.fixture.motion_bundle)

    def test_result_documents_are_copy_isolated(self):
        result, _mocks = self.build()
        run = result.run_manifest
        run["authority"]["release_authority"] = True
        documents = result.document_bytes
        documents["run-manifest.json"] = b"tampered"
        self.assertFalse(result.run_manifest["authority"]["release_authority"])
        self.assertNotEqual(b"tampered", result.document_bytes[
            "run-manifest.json"
        ])

    def test_crosswired_reviewed_source_fails_closed(self):
        fixture = self.fixture
        with fixture.pipeline_sources() as mocks:
            mocks["VerifiedReviewedMotionBundleReader.load"].return_value = replace(
                fixture.reviewed, project_id="other-project",
            )
            with self.assertRaisesRegex(
                VerifiedSpine42V3PipelineV2Error,
                "project, clip|source chain",
            ):
                self.pipeline.build(
                    fixture.motion_bundle.project_id,
                    fixture.motion_bundle.motion_instance_v3_sha256,
                    fixture.motion_bundle.bundle_sha256,
                )

    def test_rebuild_requires_issued_v2_compilation(self):
        with self.assertRaisesRegex(
            VerifiedSpine42V3PipelineV2Error, "verified P10.7a v2",
        ):
            self.pipeline.rebuild_and_verify(object())


if __name__ == "__main__":
    unittest.main()
