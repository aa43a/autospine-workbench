"""BodySwayProbeReport v1 standalone validator and schema tests."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from autospine_workbench.body_sway_probe_validation import (
    BodySwayProbeValidationError,
    body_sway_probe_report_sha256,
    require_body_sway_probe_report,
)
from autospine_workbench.body_sway_probe_sample_validation import (
    representative_sample_sha256,
)
from tests.body_sway_probe_helpers import reject_check, valid_report

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover - optional test dependency
    Draft202012Validator = None


ROOT = Path(__file__).resolve().parents[1]


class BodySwayProbeValidationTests(unittest.TestCase):
    def assert_invalid(self, mutate, *, with_mesh=True):
        document = valid_report(with_mesh=with_mesh)
        mutate(document)
        with self.assertRaises(BodySwayProbeValidationError):
            require_body_sway_probe_report(document)

    def test_valid_manual_required_report_is_canonical_and_hash_stable(self):
        document = valid_report()
        require_body_sway_probe_report(document)
        self.assertEqual("manual_visual_required", document["status"])
        self.assertEqual("blocked", document["release_gate"]["status"])
        self.assertEqual(
            len(document["sample_stream"]["rig_bone_ids"]),
            document["checks"][1]["subject_count"],
        )
        self.assertGreater(
            document["summary"]["rig_bone_count"],
            document["summary"]["overlay_bone_count"],
        )
        reordered = json.loads(json.dumps(document, sort_keys=True))
        self.assertEqual(
            body_sway_probe_report_sha256(document),
            body_sway_probe_report_sha256(reordered),
        )

    def test_each_sampled_structural_rejection_derives_top_rejection(self):
        for index in range(5):
            document = valid_report()
            reject_check(document, index)
            with self.subTest(check=document["checks"][index]["check_id"]):
                require_body_sway_probe_report(document)
                self.assertEqual("structural_rejected", document["status"])
                self.assertIn(
                    "sampled_structural_check_rejected",
                    document["release_gate"]["reason_codes"],
                )

    def test_top_level_can_never_pass_or_release(self):
        self.assert_invalid(lambda row: row.__setitem__("status", "passed"))
        self.assert_invalid(
            lambda row: row["release_gate"].__setitem__("status", "unblocked")
        )
        self.assert_invalid(
            lambda row: row["release_gate"].__setitem__("reason_codes", [])
        )
        rejected = valid_report()
        reject_check(rejected, 0)
        rejected["status"] = "manual_visual_required"
        with self.assertRaises(BodySwayProbeValidationError):
            require_body_sway_probe_report(rejected)

    def test_semantics_forbid_runtime_safety_visual_raster_and_seam_claims(self):
        fields = (
            "motion_instance_v3_emitted",
            "runtime_timeline_emitted",
            "safe_range_claimed",
            "review_input_envelope_is_safety_evidence",
            "continuous_time_safety_claimed",
            "visual_quality_claimed",
            "raster_truth_claimed",
            "inter_attachment_seam_safety_claimed",
        )
        for field in fields:
            with self.subTest(field=field):
                self.assert_invalid(
                    lambda row, name=field: row["semantics"].__setitem__(name, True)
                )
        self.assert_invalid(
            lambda row: row["semantics"].__setitem__(
                "manual_runtime_preview_required", False
            )
        )
        self.assert_invalid(
            lambda row: row["semantics"].__setitem__(
                "review_input_envelope_max_deg", 9.0
            )
        )
        self.assert_invalid(
            lambda row: row["semantics"].__setitem__(
                "bulk_evidence_digests_are_compiler_seals", False
            )
        )
        self.assert_invalid(
            lambda row: row["semantics"].__setitem__(
                "bulk_evidence_standalone_replay_claimed", True
            )
        )

    def test_seam_and_visual_checks_cannot_be_fabricated(self):
        for index in (5, 6):
            with self.subTest(index=index):
                self.assert_invalid(lambda row, i=index: row["checks"][i].update({
                    "status": "passed",
                    "reason_code": "sampled_check_passed",
                    "subject_count": 1,
                    "sample_count": 65,
                    "evidence_sha256": "e" * 64,
                }))
        self.assert_invalid(
            lambda row: row["checks"][5].__setitem__(
                "reason_code", "automatic_alpha_gap_passed"
            )
        )
        self.assert_invalid(
            lambda row: row["checks"][6].__setitem__(
                "reason_code", "software_raster_passed"
            )
        )

    def test_no_mesh_is_explicit_reviewed_noop_not_a_safety_claim(self):
        document = valid_report(with_mesh=False)
        require_body_sway_probe_report(document)
        mesh, continuity = document["checks"][2], document["checks"][4]
        self.assertEqual("not_applicable", mesh["status"])
        self.assertEqual("reviewed_noop", mesh["reason_code"])
        self.assertEqual("not_applicable", continuity["status"])
        self.assertEqual(0, document["summary"]["mesh_attachment_count"])
        self.assertEqual("manual_visual_required", document["status"])
        self.assertFalse(document["semantics"]["safe_range_claimed"])
        self.assert_invalid(
            lambda row: row["checks"][2].update({
                "status": "passed", "reason_code": "sampled_check_passed",
                "evidence_sha256": "f" * 64,
            }),
            with_mesh=False,
        )

    def test_source_and_nested_identity_inventories_are_exact(self):
        cases = [
            lambda row: row.__setitem__("extra", True),
            lambda row: row["source"].pop("idle_behavior_decision_sha256"),
            lambda row: row["source"].__setitem__("extra", "a" * 64),
            lambda row: row["source"]["p3"].pop("rig_sha256"),
            lambda row: row["source"]["p5"].__setitem__("extra", "a" * 64),
            lambda row: row["source"]["p9"].__setitem__(
                "bundle_sha256", "A" * 64
            ),
            lambda row: row["source"].__setitem__(
                "layer_manifest_sha256", "f" * 64
            ),
        ]
        for mutate in cases:
            with self.subTest(mutate=mutate):
                self.assert_invalid(mutate)

    def test_only_adjusted_pending_body_sway_selection_is_probeable(self):
        cases = [
            lambda row: row["selection"].__setitem__("feature_id", "blink"),
            lambda row: row["selection"].__setitem__("action", "reject"),
            lambda row: row["selection"].__setitem__("probe_status", "complete"),
            lambda row: row["selection"].__setitem__("extra", True),
            lambda row: row["selection"]["parameters"].__setitem__("cycles", 0),
            lambda row: row["selection"]["parameters"][
                "per_bone_amplitude_deg"
            ].reverse(),
            lambda row: row["selection"]["parameters"][
                "per_bone_phase_fraction"
            ][0].__setitem__("bone_id", "other"),
            lambda row: row["selection"]["parameters"][
                "per_bone_amplitude_deg"
            ][0].__setitem__("value", float("nan")),
        ]
        for mutate in cases:
            with self.subTest(mutate=mutate):
                self.assert_invalid(mutate)

    def test_prober_timing_and_schedule_are_pinned_and_bounded(self):
        cases = [
            lambda row: row["prober"]["config"].__setitem__(
                "uniform_samples_per_cycle", 16
            ),
            lambda row: row["prober"]["config"].__setitem__(
                "fixed_sample_step_ticks", 100_000
            ),
            lambda row: row["timing"].__setitem__("ticks_per_second", 1000),
            lambda row: row["timing"].__setitem__("loop", 1),
            lambda row: row["schedule"].__setitem__("sample_count", 65_537),
            lambda row: row["schedule"].__setitem__("first_tick", 1),
            lambda row: row["schedule"].__setitem__("last_tick", 999_999),
            lambda row: row["schedule"].__setitem__("extra", True),
        ]
        for mutate in cases:
            with self.subTest(mutate=mutate):
                self.assert_invalid(mutate)

    def test_stream_inventories_representatives_and_numbers_are_canonical(self):
        cases = [
            lambda row: row["sample_stream"]["rig_bone_ids"].reverse(),
            lambda row: row["sample_stream"]["rotation_bone_ids"].reverse(),
            lambda row: row["sample_stream"]["overlay_bone_ids"].reverse(),
            lambda row: row["sample_stream"]["rig_bone_ids"].remove(
                "arm.left"
            ),
            lambda row: row["sample_stream"]["rotation_bone_ids"].remove(
                "pelvis-spine"
            ),
            lambda row: row["sample_stream"]["attachments"].reverse(),
            lambda row: row["sample_stream"]["attachments"].append(
                deepcopy(row["sample_stream"]["attachments"][0])
            ),
            lambda row: row["sample_stream"]["representative_samples"].reverse(),
            lambda row: row["sample_stream"]["representative_samples"][0]
            .__setitem__("tick", 1),
            lambda row: row["sample_stream"]["representative_samples"][0][
                "overlay_rotation_deg"
            ][0].__setitem__("value", 1.0000000001),
            lambda row: row["sample_stream"]["representative_samples"][0][
                "overlay_rotation_deg"
            ][0].__setitem__("value", float("inf")),
            lambda row: row["sample_stream"]["representative_samples"][0][
                "overlay_rotation_deg"
            ][3].__setitem__("value", 2.0),
            lambda row: row["sample_stream"]["representative_samples"][-1][
                "overlay_rotation_deg"
            ][1].__setitem__("value", -2.0),
            lambda row: row["sample_stream"]["representative_samples"][0][
                "base_rotation_deg"
            ][0].__setitem__("value", 6.0),
            lambda row: row["sample_stream"]["representative_samples"][0][
                "combined_rotation_deg"
            ][0].__setitem__("value", 6.0),
            lambda row: row["sample_stream"]["representative_samples"][0][
                "root_translation_xy"
            ].__setitem__(0, float("nan")),
            lambda row: row["sample_stream"]["representative_samples"][0]
            .__setitem__("sample_sha256", "e" * 64),
            lambda row: row["sample_stream"]["representative_samples"][0]
            .__setitem__("extra", True),
            lambda row: row["sample_stream"]["representative_samples"][-1][
                "root_translation_xy"
            ].__setitem__(0, 4.0),
        ]
        for mutate in cases:
            with self.subTest(mutate=mutate):
                self.assert_invalid(mutate)

    def test_visible_pose_invariants_cannot_be_hidden_by_rehashing(self):
        cases = []

        non_overlay = valid_report()
        sample = non_overlay["sample_stream"]["representative_samples"][0]
        sample["overlay_rotation_deg"][0]["value"] = 0.1
        sample["combined_rotation_deg"][0]["value"] = 5.1
        cases.append(non_overlay)

        bad_sum = valid_report()
        sample = bad_sum["sample_stream"]["representative_samples"][0]
        sample["combined_rotation_deg"][0]["value"] = 6.0
        cases.append(bad_sum)

        bad_loop = valid_report()
        sample = bad_loop["sample_stream"]["representative_samples"][-1]
        sample["root_translation_xy"][0] = 4.0
        cases.append(bad_loop)

        for document in cases:
            sample = document["sample_stream"]["representative_samples"][-1]
            if document is not bad_loop:
                sample = document["sample_stream"]["representative_samples"][0]
            sample["sample_sha256"] = representative_sample_sha256(sample)
            with self.subTest(sample=sample):
                with self.assertRaises(BodySwayProbeValidationError):
                    require_body_sway_probe_report(document)

    def test_overlay_envelope_uses_the_same_nine_digit_quantization(self):
        for amplitude in (0.0000000005, 0.0000000006):
            document = valid_report()
            amplitudes = document["selection"]["parameters"][
                "per_bone_amplitude_deg"
            ]
            amplitudes[0]["value"] = amplitude
            quantized = round(amplitude, 9)
            for sample in document["sample_stream"]["representative_samples"]:
                sample["overlay_rotation_deg"][3]["value"] = quantized
                sample["combined_rotation_deg"][3]["value"] = round(
                    1.0 + quantized, 9
                )
                sample["sample_sha256"] = representative_sample_sha256(sample)
            with self.subTest(amplitude=amplitude, quantized=quantized):
                require_body_sway_probe_report(document)

    def test_check_order_counts_status_and_summary_are_derived(self):
        cases = [
            lambda row: row["checks"].reverse(),
            lambda row: row["checks"].pop(),
            lambda row: row["checks"][1].__setitem__("subject_count", 3),
            lambda row: row["checks"][1].__setitem__("subject_count", 4),
            lambda row: row["checks"][1].__setitem__("sample_count", 64),
            lambda row: row["checks"][1].__setitem__("failure_count", 1),
            lambda row: row["checks"][1].__setitem__("evidence_sha256", None),
            lambda row: row["summary"].__setitem__("passed_check_count", 4),
            lambda row: row["summary"].__setitem__("check_count", 7.0),
            lambda row: row["summary"].__setitem__("rig_bone_count", 4),
            lambda row: row["summary"].__setitem__("rotation_bone_count", 4),
            lambda row: row["summary"].__setitem__("extra", 0),
        ]
        for mutate in cases:
            with self.subTest(mutate=mutate):
                self.assert_invalid(mutate)

    def test_non_loop_requires_explicit_not_applicable_loop_check(self):
        document = valid_report()
        document["timing"]["loop"] = False
        document["checks"][0] = {
            "check_id": "loop_closure", "status": "not_applicable",
            "reason_code": "clip_not_looping", "subject_count": 0,
            "sample_count": 0, "failure_count": 0, "evidence_sha256": None,
        }
        document["summary"].update({
            "passed_check_count": 4, "not_applicable_check_count": 1,
        })
        endpoint = document["sample_stream"]["representative_samples"][-1]
        endpoint["base_rotation_deg"][0]["value"] = 6.0
        endpoint["combined_rotation_deg"][0]["value"] = 6.0
        endpoint["root_translation_xy"][0] = 4.0
        endpoint["sample_sha256"] = representative_sample_sha256(endpoint)
        require_body_sway_probe_report(document)

        not_closed = deepcopy(document)
        endpoint = not_closed["sample_stream"]["representative_samples"][-1]
        endpoint["overlay_rotation_deg"][3]["value"] = 1.0
        endpoint["combined_rotation_deg"][3]["value"] = 2.0
        endpoint["sample_sha256"] = representative_sample_sha256(endpoint)
        with self.assertRaises(BodySwayProbeValidationError):
            require_body_sway_probe_report(not_closed)

    def test_byte_limit_non_mapping_and_non_json_fail_closed(self):
        with patch(
            "autospine_workbench.body_sway_probe_validation.MAX_DOCUMENT_BYTES", 1,
        ):
            with self.assertRaises(BodySwayProbeValidationError):
                require_body_sway_probe_report(valid_report())
        with self.assertRaises(BodySwayProbeValidationError):
            require_body_sway_probe_report(None)
        self.assert_invalid(lambda row: row.__setitem__("project_id", object()))

    @unittest.skipIf(Draft202012Validator is None, "jsonschema is optional")
    def test_schema_parity_for_valid_and_forbidden_claims(self):
        schema = json.loads(
            (ROOT / "schemas" / "body-sway-probe-report-v1.schema.json")
            .read_text(encoding="utf-8")
        )
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        validator.validate(valid_report())
        validator.validate(valid_report(with_mesh=False))
        mutations = [
            lambda row: row.__setitem__("status", "passed"),
            lambda row: row["release_gate"].__setitem__("status", "unblocked"),
            lambda row: row["semantics"].__setitem__("safe_range_claimed", True),
            lambda row: row["checks"][5].__setitem__("status", "passed"),
            lambda row: row["checks"][6].__setitem__(
                "reason_code", "automatic_visual_pass"
            ),
            lambda row: row["selection"].__setitem__("action", "reject"),
            lambda row: row["sample_stream"].pop("rig_bone_ids"),
            lambda row: row["sample_stream"]["representative_samples"][0]
            .__setitem__("extra", True),
        ]
        for mutate in mutations:
            document = valid_report()
            mutate(document)
            with self.subTest(mutate=mutate):
                with self.assertRaises(BodySwayProbeValidationError):
                    require_body_sway_probe_report(document)
                self.assertTrue(tuple(validator.iter_errors(document)))


if __name__ == "__main__":
    unittest.main()
