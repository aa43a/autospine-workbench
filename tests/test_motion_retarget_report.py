"""P5 deterministic kinematic retarget evidence tests."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover - optional test extra
    Draft202012Validator = None

from autospine_workbench.motion_bundle_reader import (  # noqa: E402
    VerifiedMotionBundleReader,
)
from autospine_workbench.motion_bundle_store import MotionBundleStore  # noqa: E402
from autospine_workbench.motion_retarget_compiler import (  # noqa: E402
    compile_motion_instance,
)
from autospine_workbench.motion_retarget_report import (  # noqa: E402
    MotionRetargetReportError,
    build_motion_retarget_report,
    require_motion_retarget_report,
)
from autospine_workbench.motion_target_profile import (  # noqa: E402
    compile_motion_target_profile,
)
from tests.test_motion_bundle_contract import payload  # noqa: E402
from tests.test_motion_target_profile import full_rig, pair  # noqa: E402


def encode(value):
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    )


class MotionRetargetReportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.state = Path(self.temporary.name) / "state"
        self.profile = compile_motion_target_profile(*pair())

    def verified(self, clip_id):
        published = MotionBundleStore(self.state).publish(*payload(clip_id))
        return VerifiedMotionBundleReader(self.state).load(
            published.clip_sha256, published.bundle_sha256
        )

    def artifacts(self, clip_id, profile=None):
        profile = profile or self.profile
        verified = self.verified(clip_id)
        retargeted = compile_motion_instance(verified, profile)
        report = build_motion_retarget_report(verified, profile, retargeted)
        return verified, retargeted, report

    def require(self, report, verified, retargeted, profile=None):
        require_motion_retarget_report(
            report,
            verified_motion=verified,
            target_profile=profile or self.profile,
            retargeted=retargeted,
        )

    def test_idle_records_pinned_finite_loop_and_contact_evidence(self):
        verified, retargeted, report = self.artifacts("idle")
        document = report.document
        self.require(document, verified, retargeted)
        self.assertEqual("passed", document["status"])
        self.assertEqual(50_000, document["sampler"]["step_ticks"])
        self.assertEqual(41, document["sampler"]["sample_count"])
        self.assertEqual(17, document["finite_pose"]["bone_count"])
        self.assertEqual(697, document["finite_pose"]["world_bone_sample_count"])
        self.assertGreaterEqual(document["finite_pose"]["max_abs_rotation_deg"], 90.0)
        self.assertEqual(0.5, document["finite_pose"]["max_root_translation_px"])
        self.assertEqual("passed", document["loop_closure"]["result"])
        self.assertLessEqual(document["loop_closure"]["maximum_numeric_error"], 1e-8)
        self.assertEqual(0, document["ik"]["track_count"])
        self.assertEqual(2, document["contacts"]["preserved_count"])
        self.assertEqual(retargeted.instance_sha256,
                         document["source"]["instance_sha256"])
        self.assertEqual(retargeted.run_document_sha256,
                         document["source"]["retarget_run_document_sha256"])

    def test_wave_rechecks_ik_setup_keys_and_marks_loop_not_applicable(self):
        verified, retargeted, report = self.artifacts("wave.left")
        document = report.document
        self.require(document, verified, retargeted)
        self.assertEqual("not_applicable", document["loop_closure"]["result"])
        self.assertEqual(1, document["ik"]["track_count"])
        self.assertEqual(6, document["ik"]["key_count"])
        self.assertEqual(2, document["ik"]["setup_key_count"])
        self.assertEqual("arm.left", document["ik"]["tracks"][0]["handle_id"])
        self.assertLessEqual(document["ik"]["maximum_effector_error_px"], 1e-8)
        self.assertEqual(document["contacts"]["source_count"],
                         document["contacts"]["preserved_count"])

    def test_report_is_deterministic_frozen_isolated_and_target_specific(self):
        verified, retargeted, first = self.artifacts("wave.left")
        second = build_motion_retarget_report(verified, self.profile, retargeted)
        self.assertEqual(first, second)
        self.assertEqual(first.sha256, second.sha256)

        changed = first.document
        changed["ik"]["tracks"].clear()
        self.assertEqual(1, len(first.document["ik"]["tracks"]))
        with self.assertRaises(FrozenInstanceError):
            first._canonical_json = "{}"  # type: ignore[misc]

        shifted = full_rig()
        shifted["bones"][0]["setup"]["x"] += 17
        profile = compile_motion_target_profile(*pair(rig=shifted))
        other_retargeted = compile_motion_instance(verified, profile)
        other = build_motion_retarget_report(verified, profile, other_retargeted)
        self.assertNotEqual(first.sha256, other.sha256)
        self.assertNotEqual(
            first.document["source"]["target_profile_sha256"],
            other.document["source"]["target_profile_sha256"],
        )

    def test_instance_marker_and_run_tamper_fail_exact_rebuild(self):
        verified, retargeted, _report = self.artifacts("wave.left")
        instance = retargeted.instance
        instance["tracks"][0]["keys"][1]["value"] += 0.25
        changed_instance = replace(retargeted, _instance_json=encode(instance))

        marker = retargeted.instance
        marker["markers"][0]["end_tick"] -= 1
        changed_marker = replace(retargeted, _instance_json=encode(marker))

        run = retargeted.run
        run["output"]["instance_sha256"] = "f" * 64
        changed_run = replace(retargeted, _run_json=encode(run))
        for changed in (changed_instance, changed_marker, changed_run):
            with self.subTest(changed=changed), self.assertRaisesRegex(
                MotionRetargetReportError, "differs"
            ):
                build_motion_retarget_report(verified, self.profile, changed)

    def test_sampled_ik_error_and_loop_closure_error_fail_gate(self):
        wave_verified = self.verified("wave.left")
        wave = compile_motion_instance(wave_verified, self.profile)
        from autospine_workbench.motion_retarget_report import sample_instance_pose
        real_sample = sample_instance_pose

        def bad_ik(*args, **kwargs):
            pose = deepcopy(real_sample(*args, **kwargs))
            if kwargs["tick"] == 400_000:
                pose["forearm.left"]["endpoint_xy"][0] += 1e-5
            return pose

        with patch(
            "autospine_workbench.motion_retarget_report.sample_instance_pose",
            side_effect=bad_ik,
        ), self.assertRaisesRegex(MotionRetargetReportError, "effector"):
            build_motion_retarget_report(wave_verified, self.profile, wave)

        idle_verified = self.verified("idle")
        idle = compile_motion_instance(idle_verified, self.profile)

        def bad_loop(*args, **kwargs):
            pose = deepcopy(real_sample(*args, **kwargs))
            if kwargs["tick"] == 2_000_000:
                pose["root-pelvis"]["origin_xy"][0] += 1e-5
            return pose

        with patch(
            "autospine_workbench.motion_retarget_report.sample_instance_pose",
            side_effect=bad_loop,
        ), self.assertRaisesRegex(MotionRetargetReportError, "close"):
            build_motion_retarget_report(idle_verified, self.profile, idle)

    def test_report_tamper_nonfinite_and_resource_drift_fail(self):
        verified, retargeted, report = self.artifacts("wave.left")
        mutations = (
            lambda value: value["source"].update(instance_sha256="f" * 64),
            lambda value: value["ik"].update(maximum_effector_error_px=1e-7),
            lambda value: value["finite_pose"].update(max_abs_rotation_deg=math.nan),
            lambda value: value["sampler"].update(sample_count=50_001),
            lambda value: value.update(latest=True),
            lambda value: value["contacts"].update(preserved_count=1),
        )
        for mutate in mutations:
            changed = report.document
            mutate(changed)
            with self.subTest(mutate=mutate), self.assertRaises(
                MotionRetargetReportError
            ):
                self.require(changed, verified, retargeted)

    @unittest.skipIf(Draft202012Validator is None, "install the test extra")
    def test_schema_is_valid_and_accepts_idle_and_wave(self):
        schema = json.loads(
            (ROOT / "schemas" / "motion-retarget-report-v1.schema.json")
            .read_text("utf-8")
        )
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        for clip_id in ("idle", "wave.left"):
            _verified, _retargeted, report = self.artifacts(clip_id)
            self.assertEqual([], list(validator.iter_errors(report.document)))


if __name__ == "__main__":
    unittest.main()
