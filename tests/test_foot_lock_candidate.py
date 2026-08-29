"""P9.2 target-specific foot-lock candidate contract tests."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover - optional test extra
    Draft202012Validator = None

from autospine_workbench.foot_lock_candidate import (  # noqa: E402
    FootLockCandidateError,
    compile_foot_lock_candidates,
)
from autospine_workbench.foot_lock_candidate_validation import (  # noqa: E402
    FootLockCandidateValidationError,
    require_foot_lock_candidates,
)
from autospine_workbench.motion_instance_validation import (  # noqa: E402
    instance_sha256,
)
from autospine_workbench.motion_mesh_regression import (  # noqa: E402
    build_motion_mesh_regression,
)
from autospine_workbench.motion_retarget_bundle_contract import (  # noqa: E402
    DOCUMENT_NAMES,
    build_motion_retarget_bundle_contract,
)
from autospine_workbench.motion_retarget_bundle_integrity import (  # noqa: E402
    VerifiedMotionRetargetBundle,
)
from autospine_workbench.motion_retarget_compiler import (  # noqa: E402
    compile_motion_instance,
)
from autospine_workbench.motion_retarget_report import (  # noqa: E402
    build_motion_retarget_report,
)
from autospine_workbench.motion_retarget_run import (  # noqa: E402
    retarget_run_document_sha256,
)
from autospine_workbench.projected_motion_bundle_reader import (  # noqa: E402
    VerifiedProjectedMotionBundleReader,
)
from tests.p5_p6_pipeline_helpers import exact_motion_target  # noqa: E402
from tests.projected_motion_bundle_helpers import ProjectedBundleFixture  # noqa: E402
from tests.test_motion_three_rig_gate import (  # noqa: E402
    ASYMMETRIC_SETUP,
    rig_from_setup,
    tall_asymmetric_rig,
)


def _verified_p5(motion, rig, *, marker_start: int | None = None):
    mesh, target = exact_motion_target(rig)
    retargeted = compile_motion_instance(motion, target)
    report = build_motion_retarget_report(motion, target, retargeted).document
    mesh_report = build_motion_mesh_regression(
        retargeted.instance, target.document, mesh
    ).document
    instance, run = retargeted.instance, retargeted.run
    if marker_start is not None:
        instance["markers"][0]["start_tick"] = marker_start
        new_instance_sha = instance_sha256(instance)
        run["output"]["instance_sha256"] = new_instance_sha
        new_run_sha = retarget_run_document_sha256(run)
        report["source"]["instance_sha256"] = new_instance_sha
        report["source"]["retarget_run_document_sha256"] = new_run_sha
        mesh_report["source"]["instance_sha256"] = new_instance_sha
    values = (target.document, instance, run, report, mesh_report)
    contract = build_motion_retarget_bundle_contract(
        target.document["project_id"], *values
    )
    target_source, motion_source = target.document["source"], instance["source"]
    sources = (
        ("p3_rig_sha256", target_source["p3"]["rig_sha256"]),
        ("p3_bundle_sha256", target_source["p3"]["bundle_sha256"]),
        ("p4_profile_sha256", target_source["p4_profile_sha256"]),
        ("p4_bundle_sha256", target_source["p4_bundle_sha256"]),
        ("motion_clip_sha256", motion_source["motion_ir_sha256"]),
        ("motion_bundle_sha256", motion_source["motion_bundle_sha256"]),
    )
    return VerifiedMotionRetargetBundle(
        path=Path("synthetic-p5"),
        project_id=contract.project_id,
        clip_id=contract.clip_id,
        target_profile_sha256=contract.target_profile_sha256,
        instance_sha256=contract.instance_sha256,
        run_document_sha256=contract.run_document_sha256,
        retarget_report_sha256=contract.report_sha256,
        mesh_regression_sha256=contract.mesh_report_sha256,
        bundle_sha256=contract.bundle_sha256,
        _source_items=sources,
        _document_items=tuple(
            (name, contract.document_bytes[name]) for name in DOCUMENT_NAMES
        ),
    )


class FootLockCandidateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.fixture = ProjectedBundleFixture(Path(self.temporary.name))
        published = self.fixture.publish()
        self.p8 = VerifiedProjectedMotionBundleReader(self.fixture.state).load(
            published.projected_motion_sha256, published.bundle_sha256
        )
        self.rig = rig_from_setup(ASYMMETRIC_SETUP)
        self.p5 = _verified_p5(self.fixture.p7, self.rig)

    def compile(self, *, correction=100.0, residual=1e9, p5=None):
        return compile_foot_lock_candidates(
            self.p8, p5 or self.p5,
            max_correction_reference_ratio=correction,
            max_residual_px=residual,
        )

    def test_deterministic_single_dual_and_unconstrained_samples(self):
        before = (deepcopy(self.p8.projected_motion), deepcopy(self.p5.motion_instance))
        first, second = self.compile(), self.compile()
        self.assertEqual(first, second)
        self.assertEqual(first.sha256, second.sha256)
        self.assertEqual(before, (self.p8.projected_motion, self.p5.motion_instance))
        document = first.document
        self.assertEqual("candidate_only", document["policy"]["mode"])
        self.assertEqual("review_required", document["policy"]["apply_policy"])
        self.assertFalse(document["policy"]["decision_emitted"])
        self.assertFalse(document["policy"]["runtime_timeline_emitted"])
        self.assertEqual("unresolved", document["policy"]["release"])

        single, dual, free = document["samples"]
        self.assertEqual("single_support", single["support_state"])
        self.assertEqual([0.0, 0.0], single["correction_candidate_px"])
        self.assertAlmostEqual(0.0, single["maximum_residual_px"])
        self.assertEqual("dual_support", dual["support_state"])
        self.assertGreater(dual["maximum_residual_px"], 0.0)
        left, right = dual["observations"]
        for axis in range(2):
            self.assertAlmostEqual(
                0.0,
                left["residual_after_candidate_px"][axis]
                + right["residual_after_candidate_px"][axis],
                places=7,
            )
        self.assertEqual("unconstrained", free["state"])
        self.assertIsNone(free["correction_candidate_px"])
        self.assertEqual([], free["observations"])
        require_foot_lock_candidates(
            document, projected_bundle=self.p8, retarget_bundle=self.p5
        )

    def test_thresholds_reject_without_clipping_raw_evidence(self):
        admitted = self.compile().document
        limited = self.compile(correction=1e-8).document
        conflicted = self.compile(residual=0.0).document
        self.assertEqual("rejected_limit", limited["summary"]["status"])
        self.assertEqual("rejected_conflict", conflicted["summary"]["status"])
        self.assertEqual(
            admitted["samples"][1]["correction_candidate_px"],
            limited["samples"][1]["correction_candidate_px"],
        )
        self.assertEqual(
            admitted["samples"][1]["observations"],
            conflicted["samples"][1]["observations"],
        )

    def test_exact_cross_binding_and_off_frame_marker_fail_closed(self):
        changed = deepcopy(self.compile().document)
        changed["source"]["target_profile_sha256"] = "f" * 64
        with self.assertRaises(FootLockCandidateValidationError):
            require_foot_lock_candidates(
                changed, projected_bundle=self.p8, retarget_bundle=self.p5
            )
        off_frame = _verified_p5(self.fixture.p7, self.rig, marker_start=1)
        with self.assertRaisesRegex(FootLockCandidateError, "absent from P8"):
            self.compile(p5=off_frame)

    def test_sample_frame_index_and_discrete_summary_are_exact(self):
        document = self.compile().document
        float_index = deepcopy(document)
        float_index["samples"][0]["source_frame_index"] = 0.0
        with self.assertRaisesRegex(
            FootLockCandidateValidationError, "schedule"
        ):
            require_foot_lock_candidates(float_index)
        float_count = deepcopy(document)
        float_count["summary"]["sample_count"] = float(
            float_count["summary"]["sample_count"]
        )
        with self.assertRaisesRegex(
            FootLockCandidateValidationError, "summary"
        ):
            require_foot_lock_candidates(float_count)

    def test_three_rigs_are_target_specific(self):
        rigs = (
            self.rig,
            rig_from_setup(ASYMMETRIC_SETUP, x_offset=37),
            tall_asymmetric_rig(),
        )
        reports = [self.compile(p5=_verified_p5(self.fixture.p7, rig))
                   for rig in rigs]
        self.assertEqual(3, len({report.sha256 for report in reports}))
        self.assertEqual(3, len({
            report.document["source"]["target_profile_sha256"]
            for report in reports
        }))
        self.assertNotEqual(
            reports[0].document["samples"][1]["correction_candidate_px"],
            reports[2].document["samples"][1]["correction_candidate_px"],
        )

    @unittest.skipIf(Draft202012Validator is None, "jsonschema is optional")
    def test_schema_accepts_compiled_report(self):
        schema = json.loads(
            (ROOT / "schemas" / "foot-lock-candidates-v1.schema.json")
            .read_text(encoding="utf-8")
        )
        Draft202012Validator(schema).validate(self.compile().document)


if __name__ == "__main__":
    unittest.main()
