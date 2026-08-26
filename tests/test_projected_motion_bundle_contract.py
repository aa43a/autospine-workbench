"""Pure contract tests for immutable ProjectedMotionIR bundles."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.kimodo_camera_projection import (  # noqa: E402
    compile_verified_kimodo_projection,
)
from autospine_workbench.projected_motion_bundle_contract import (  # noqa: E402
    BUNDLE_ADDRESS_DOMAIN,
    DOCUMENT_NAMES,
    ProjectedMotionBundleContractError,
    build_projected_motion_bundle_contract,
)
from autospine_workbench.projected_motion_compile_run import (  # noqa: E402
    build_projected_motion_compile_run,
)
from autospine_workbench.projected_motion_legacy import (  # noqa: E402
    compile_projected_motion_to_motion_ir,
)
from tests.test_kimodo_camera_projection import (  # noqa: E402
    camera_document,
    verified_fixture,
)


def bundle_artifacts():
    source, mapping = verified_fixture()
    camera = camera_document(mapping)
    projected = compile_verified_kimodo_projection(source, camera)
    legacy = compile_projected_motion_to_motion_ir(projected.document)
    run = build_projected_motion_compile_run(
        source, camera, projected, legacy
    )
    return camera, projected.document, run.document


class ProjectedMotionBundleContractTests(unittest.TestCase):
    def test_contract_has_fixed_inventory_and_stable_address(self):
        camera, projected, run = bundle_artifacts()
        first = build_projected_motion_bundle_contract(camera, projected, run)
        second = build_projected_motion_bundle_contract(
            deepcopy(camera), deepcopy(projected), deepcopy(run)
        )
        self.assertEqual(first, second)
        self.assertEqual(DOCUMENT_NAMES, first.inventory)
        self.assertEqual(first.camera_sha256, run["camera"]["camera_sha256"])
        self.assertEqual(
            first.projected_motion_sha256,
            run["output"]["projected_motion_ir_sha256"],
        )
        self.assertEqual(
            first.legacy_motion_sha256,
            projected["source"]["motion_ir_sha256"],
        )
        self.assertIn("projected-motion", BUNDLE_ADDRESS_DOMAIN)
        self.assertEqual(camera, first.camera)
        self.assertEqual(projected, first.projected_motion)
        self.assertEqual(run, first.run_manifest)

    def test_each_document_change_changes_or_rejects_address(self):
        camera, projected, run = bundle_artifacts()
        baseline = build_projected_motion_bundle_contract(
            camera, projected, run
        )
        changed_camera = deepcopy(camera)
        changed_camera["camera_id"] = "other-camera"
        with self.assertRaises(ProjectedMotionBundleContractError):
            build_projected_motion_bundle_contract(
                changed_camera, projected, run
            )
        changed_run = deepcopy(run)
        changed_run["validation"]["max_global_matrix_error"] += 1e-12
        changed = build_projected_motion_bundle_contract(
            camera, projected, changed_run
        )
        self.assertNotEqual(baseline.bundle_sha256, changed.bundle_sha256)
        self.assertEqual(
            baseline.projected_motion_sha256, changed.projected_motion_sha256
        )

    def test_cross_wired_output_and_collapsed_evidence_fail_closed(self):
        camera, projected, run = bundle_artifacts()
        changed = deepcopy(run)
        changed["output"]["projected_motion_ir_sha256"] = "a" * 64
        with self.assertRaises(ProjectedMotionBundleContractError):
            build_projected_motion_bundle_contract(camera, projected, changed)

        collapsed = deepcopy(projected)
        collapsed_track = collapsed["segment_tracks"][0]
        sample = collapsed_track["samples"][0]
        sample.update(
            projected_vector_normalized=[0.0, 0.0],
            projected_length_normalized=0.0,
            foreshortening_ratio=0.0,
            depth_cosine=1.0,
            end_depth_root_relative_normalized=
                sample["start_depth_root_relative_normalized"]
                + sample["source_length_normalized"],
            midpoint_depth_root_relative_normalized=
                sample["start_depth_root_relative_normalized"]
                + sample["source_length_normalized"] / 2.0,
            projection_state="collapsed",
        )
        collapsed_track["setup_projected_length_normalized"] = 0.0
        with self.assertRaisesRegex(
            ProjectedMotionBundleContractError, "collapsed"
        ):
            build_projected_motion_bundle_contract(camera, collapsed, run)

    def test_individual_document_limits_are_enforced(self):
        camera, projected, run = bundle_artifacts()
        for index, label in enumerate(DOCUMENT_NAMES):
            limits = list((16 * 1024, 64 * 1024 * 1024, 64 * 1024))
            limits[index] = 1
            with self.subTest(label=label), patch(
                "autospine_workbench.projected_motion_bundle_contract."
                "DOCUMENT_LIMITS",
                tuple(limits),
            ), self.assertRaises(ProjectedMotionBundleContractError):
                build_projected_motion_bundle_contract(camera, projected, run)


if __name__ == "__main__":
    unittest.main()
