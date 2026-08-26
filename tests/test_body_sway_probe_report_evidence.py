"""Check attribution and digest tests for body-sway bulk evidence."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.body_sway_probe_geometry import (  # noqa: E402
    evaluate_body_sway_geometry_sample,
)
from autospine_workbench.body_sway_probe_math import (  # noqa: E402
    BodySwayLoopAudit,
)
from autospine_workbench.body_sway_probe_report_evidence import (  # noqa: E402
    BodySwayProbeReportEvidenceError,
    SampleStreamSealer,
    StructuralEvidenceAccumulator,
    tick_schedule_sha256,
)
from tests.body_sway_probe_geometry_helpers import (  # noqa: E402
    exact_rig_and_target,
    sample,
)


SHA = "a" * 64


def _audit(*, loop=False, closed=True):
    return BodySwayLoopAudit(
        loop=loop, status="closed" if closed else "rejected",
        overlay_closed=True, base_rotation_closed=closed,
        combined_rotation_closed=closed, root_translation_closed=closed,
        reason_codes=() if closed else ("root_translation_not_closed",),
    )


def _inventory(rig):
    bones = tuple(sorted(row["id"] for row in rig["bones"]))
    attachments = tuple(sorted(
        (row["id"], row["type"]) for row in rig["attachments"]
    ))
    return bones, attachments


def _row(checks, check_id):
    return next(row for row in checks if row["check_id"] == check_id)


class BodySwayProbeReportEvidenceTests(unittest.TestCase):
    def test_canvas_failures_count_unique_ticks_not_vertices(self):
        rig, target = exact_rig_and_target()
        bones, attachments = _inventory(rig)
        accumulator = StructuralEvidenceAccumulator(
            rig_bone_ids=bones, attachments=attachments,
        )
        accumulator.observe(evaluate_body_sway_geometry_sample(
            rig, target, sample(tick=0)
        ))
        failed = evaluate_body_sway_geometry_sample(
            rig, target, sample(tick=1, translation=(500.0, 0.0))
        )
        self.assertGreater(len(failed.canvas_failures), 1)
        accumulator.observe(failed)
        checks = accumulator.checks(
            loop_audit=_audit(), start_pose_state_sha256=SHA,
            end_pose_state_sha256=SHA, expected_sample_count=2,
        )
        canvas = _row(checks, "sampled_canvas_containment")
        self.assertEqual("rejected", canvas["status"])
        self.assertEqual(1, canvas["failure_count"])
        self.assertEqual(2, canvas["sample_count"])

    def test_mesh_deformation_is_attributed_without_forging_seam_evidence(self):
        rig, target = exact_rig_and_target(failing_mesh=True)
        bones, attachments = _inventory(rig)
        accumulator = StructuralEvidenceAccumulator(
            rig_bone_ids=bones, attachments=attachments,
        )
        result = evaluate_body_sway_geometry_sample(
            rig, target, sample(base={"calf.left": 90.0}, tick=0)
        )
        accumulator.observe(result)
        checks = accumulator.checks(
            loop_audit=_audit(), start_pose_state_sha256=SHA,
            end_pose_state_sha256=SHA, expected_sample_count=1,
        )
        mesh = _row(checks, "sampled_mesh_deformation")
        self.assertEqual("rejected", mesh["status"])
        self.assertEqual(1, mesh["failure_count"])
        seam = _row(checks, "inter_attachment_seams")
        self.assertEqual("unobservable", seam["status"])
        self.assertIsNone(seam["evidence_sha256"])

    def test_stream_and_check_seals_are_deterministic_and_domain_separated(self):
        first = SampleStreamSealer(
            rig_bone_ids=("a",), rotation_bone_ids=("a",),
            overlay_bone_ids=("a",), attachments=(),
        )
        second = SampleStreamSealer(
            rig_bone_ids=("a",), rotation_bone_ids=("a",),
            overlay_bone_ids=("a",), attachments=(),
        )
        for stream in (first, second):
            stream.observe(0, "1" * 64)
            stream.observe(1, "2" * 64)
        self.assertEqual(first.finish(2), second.finish(2))
        self.assertNotEqual(first.finish(2), tick_schedule_sha256((0, 1)))
        changed = SampleStreamSealer(
            rig_bone_ids=("a",), rotation_bone_ids=("a",),
            overlay_bone_ids=("a",), attachments=(),
        )
        changed.observe(0, "1" * 64)
        changed.observe(1, "3" * 64)
        self.assertNotEqual(first.finish(2), changed.finish(2))

    def test_inventory_drift_and_tick_reuse_fail_closed(self):
        rig, target = exact_rig_and_target()
        bones, attachments = _inventory(rig)
        result = evaluate_body_sway_geometry_sample(rig, target, sample(tick=0))
        accumulator = StructuralEvidenceAccumulator(
            rig_bone_ids=bones, attachments=attachments,
        )
        accumulator.observe(result)
        with self.assertRaises(BodySwayProbeReportEvidenceError):
            accumulator.observe(result)
        forged = StructuralEvidenceAccumulator(
            rig_bone_ids=bones[:-1], attachments=attachments,
        )
        with self.assertRaisesRegex(
            BodySwayProbeReportEvidenceError, "inventory"
        ):
            forged.observe(result)

    def test_loop_check_binds_audit_and_visible_endpoint_truth(self):
        rig, target = exact_rig_and_target()
        bones, attachments = _inventory(rig)
        accumulator = StructuralEvidenceAccumulator(
            rig_bone_ids=bones, attachments=attachments,
        )
        accumulator.observe(evaluate_body_sway_geometry_sample(
            rig, target, sample(tick=0)
        ))
        rejected = accumulator.checks(
            loop_audit=_audit(loop=True, closed=False),
            start_pose_state_sha256="1" * 64,
            end_pose_state_sha256="2" * 64,
            expected_sample_count=1,
        )[0]
        self.assertEqual("rejected", rejected["status"])
        self.assertEqual(1, rejected["failure_count"])

        for audit, start_sha, end_sha in (
            (_audit(loop=True, closed=True), "1" * 64, "2" * 64),
            (_audit(loop=True, closed=False), "1" * 64, "1" * 64),
        ):
            with self.subTest(closed=audit.status), self.assertRaisesRegex(
                BodySwayProbeReportEvidenceError, "visible endpoint"
            ):
                accumulator.checks(
                    loop_audit=audit, start_pose_state_sha256=start_sha,
                    end_pose_state_sha256=end_sha, expected_sample_count=1,
                )
        open_overlay = replace(
            _audit(), status="rejected", overlay_closed=False,
            reason_codes=("overlay_not_closed",),
        )
        with self.assertRaisesRegex(
            BodySwayProbeReportEvidenceError, "overlay endpoints"
        ):
            accumulator.checks(
                loop_audit=open_overlay, start_pose_state_sha256="1" * 64,
                end_pose_state_sha256="1" * 64, expected_sample_count=1,
            )


if __name__ == "__main__":
    unittest.main()
