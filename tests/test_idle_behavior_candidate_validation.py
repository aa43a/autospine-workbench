"""IdleBehaviorCandidates v1 standalone validator and schema tests."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from autospine_workbench.idle_behavior_candidate_validation import (
    BODY_SWAY_PROPOSAL,
    GENERATOR,
    IdleBehaviorCandidateValidationError,
    idle_behavior_candidates_sha256,
    require_idle_behavior_candidates,
)
from autospine_workbench.idle_behavior_candidate_identity import (
    body_sway_candidate_id,
)

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover - optional test dependency
    Draft202012Validator = None


ROOT = Path(__file__).resolve().parents[1]
SHA = "a" * 64


def _source():
    p3 = {
        field: SHA for field in (
            "base_rig_sha256", "base_bundle_sha256", "layer_manifest_sha256",
            "resolved_project_sha256", "rig_sha256", "run_sha256",
            "probes_sha256", "visuals_sha256", "bundle_sha256",
        )
    }
    p5 = {
        field: SHA for field in (
            "target_profile_sha256", "instance_sha256", "run_sha256",
            "retarget_report_sha256", "mesh_regression_sha256", "bundle_sha256",
        )
    }
    p9 = {
        field: SHA for field in (
            "foot_lock_candidates_sha256", "depth_order_candidates_sha256",
            "motion_policy_decision_sha256", "reviewed_motion_policy_sha256",
            "motion_instance_v2_sha256", "run_sha256", "bundle_sha256",
        )
    }
    return {"layer_manifest_sha256": SHA, "p3": p3, "p5": p5, "p9": p9}


def _evidence():
    return {
        "layers": [
            {
                "layer_id": "layer.body", "canonical_role": "torso",
                "side": "center", "raster_sha256": SHA,
                "review_state": "reviewed",
            },
            {
                "layer_id": "layer.head", "canonical_role": "head",
                "side": "center", "raster_sha256": SHA,
                "review_state": "reviewed",
            },
        ],
        "bindings": [
            {
                "attachment_id": "attachment.body", "slot_id": "slot.body",
                "bone_id": "pelvis-spine", "image_sha256": SHA,
                "type": "mesh",
            },
            {
                "attachment_id": "attachment.head", "slot_id": "slot.head",
                "bone_id": "neck-head", "image_sha256": SHA,
                "type": "region",
            },
        ],
        "bone_ids": ["chest-neck", "neck-head", "pelvis-spine", "spine-chest"],
        "existing_tracks": [
            {"bone_id": "chest-neck", "property": "rotation"},
            {"bone_id": "pelvis-spine", "property": "translation"},
        ],
    }


def _feature(feature_id, availability, reasons, *, candidate_id=None, proposal=None):
    return {
        "feature_id": feature_id,
        "availability": availability,
        "candidate_id": candidate_id,
        "evidence": _evidence(),
        "reason_codes": reasons,
        "proposal": proposal,
    }


def valid_candidates():
    document = {
        "format": "autospine-idle-behavior-candidates",
        "format_version": 1,
        "project_id": "sample.project",
        "clip_id": "idle-01",
        "source": _source(),
        "timing": {
            "ticks_per_second": 1_000_000,
            "duration_ticks": 2_000_000,
            "loop": True,
        },
        "target_capabilities": {
            "adapter_id": "autospine-spine42-json-adapter",
            "adapter_version": "2.0.0",
            "bone_rotation": True,
            "root_translation": True,
            "draw_order": True,
            "attachment_switching": False,
            "deform": False,
            "physics": False,
            "extra_bones": False,
        },
        "generator": {
            "id": "idle-behavior-candidate-compiler",
            "version": "1.0.0",
            "candidate_id_domain": "autospine-idle-behavior-candidate-id/v1",
        },
        "semantics": {
            "mode": "candidate_only",
            "apply_policy": "review_required",
            "decision_emitted": False,
            "runtime_timeline_emitted": False,
            "generated_raster_emitted": False,
            "synthetic_visual_state_emitted": False,
            "raster_truth_claimed": False,
        },
        "features": [
            _feature("blink", "unobservable", ["single-setup-state"]),
            _feature(
                "body_sway", "candidate", ["manual-amplitude-required"],
                candidate_id=None, proposal=deepcopy(BODY_SWAY_PROPOSAL),
            ),
            _feature("hair_spring", "unsupported", ["extra-bones-unavailable"]),
            _feature("mouth", "unobservable", ["single-setup-state"]),
        ],
        "summary": {
            "status": "candidate_only", "feature_count": 4,
            "candidate_count": 1, "unobservable_count": 2,
            "unsupported_count": 1,
        },
    }
    document["features"][1]["candidate_id"] = body_sway_candidate_id(
        generator=GENERATOR,
        motion_instance_v2_sha256=SHA,
        target_profile_sha256=SHA,
        feature_id="body_sway",
        target_bone_ids=BODY_SWAY_PROPOSAL["target_bone_ids"],
    )
    return document


class IdleBehaviorCandidateValidationTests(unittest.TestCase):
    def assert_invalid(self, mutate):
        document = valid_candidates()
        mutate(document)
        with self.assertRaises(IdleBehaviorCandidateValidationError):
            require_idle_behavior_candidates(document)

    def test_valid_document_and_canonical_hash(self):
        document = valid_candidates()
        require_idle_behavior_candidates(document)
        reordered = json.loads(json.dumps(document, sort_keys=True))
        self.assertEqual(
            idle_behavior_candidates_sha256(document),
            idle_behavior_candidates_sha256(reordered),
        )

    def test_top_source_and_source_stages_are_exact(self):
        cases = [
            lambda row: row.__setitem__("extra", True),
            lambda row: row["source"].__setitem__("extra", SHA),
            lambda row: row["source"]["p3"].pop("rig_sha256"),
            lambda row: row["source"]["p5"].__setitem__("extra", SHA),
            lambda row: row["source"]["p9"].__setitem__("run_sha256", SHA.upper()),
            lambda row: row["source"].__setitem__("layer_manifest_sha256", "b" * 64),
        ]
        for mutate in cases:
            with self.subTest(mutate=mutate):
                self.assert_invalid(mutate)

    def test_timing_capabilities_generator_and_semantics_are_fixed(self):
        cases = [
            lambda row: row["timing"].__setitem__("ticks_per_second", 1000),
            lambda row: row["timing"].__setitem__("duration_ticks", 600_000_001),
            lambda row: row["timing"].__setitem__("loop", 1),
            lambda row: row["timing"].__setitem__("extra", 1),
            lambda row: row["target_capabilities"].__setitem__("deform", True),
            lambda row: row["target_capabilities"].__setitem__("physics", 0),
            lambda row: row["generator"].__setitem__("version", "1.0.1"),
            lambda row: row["semantics"].__setitem__("decision_emitted", True),
            lambda row: row["semantics"].pop("generated_raster_emitted"),
        ]
        for mutate in cases:
            with self.subTest(mutate=mutate):
                self.assert_invalid(mutate)

    def test_feature_order_and_availability_are_closed(self):
        self.assert_invalid(lambda row: row["features"].reverse())
        self.assert_invalid(lambda row: row["features"].pop())
        self.assert_invalid(
            lambda row: row["features"][0].__setitem__("availability", "accepted")
        )
        self.assert_invalid(lambda row: row["features"][0].__setitem__("extra", 1))

    def test_candidate_id_and_proposal_are_iff_candidate(self):
        cases = [
            lambda row: row["features"][1].__setitem__("candidate_id", None),
            lambda row: row["features"][1].__setitem__("proposal", None),
            lambda row: row["features"][1].__setitem__("candidate_id", "bad id"),
            lambda row: row["features"][0].__setitem__("candidate_id", "blink.01"),
            lambda row: row["features"][0].__setitem__(
                "proposal", deepcopy(BODY_SWAY_PROPOSAL)
            ),
            lambda row: row["features"][0].__setitem__("availability", "candidate"),
            lambda row: row["features"][1]["proposal"].__setitem__(
                "safe_range_evidence", "estimated"
            ),
        ]
        for mutate in cases:
            with self.subTest(mutate=mutate):
                self.assert_invalid(mutate)

    def test_candidate_id_is_recomputed_not_merely_shape_checked(self):
        cases = (
            lambda row: row["features"][1].__setitem__(
                "candidate_id", "body-sway-" + "0" * 64
            ),
            lambda row: row["source"]["p9"].__setitem__(
                "motion_instance_v2_sha256", "b" * 64
            ),
            lambda row: row["source"]["p5"].__setitem__(
                "target_profile_sha256", "b" * 64
            ),
        )
        for mutate in cases:
            with self.subTest(mutate=mutate):
                self.assert_invalid(mutate)

    def test_evidence_shapes_and_enums_fail_closed(self):
        cases = [
            lambda row: row["features"][0]["evidence"].__setitem__("extra", []),
            lambda row: row["features"][0]["evidence"]["layers"][0].__setitem__(
                "side", "front"
            ),
            lambda row: row["features"][0]["evidence"]["layers"][0].__setitem__(
                "review_state", "accepted"
            ),
            lambda row: row["features"][0]["evidence"]["bindings"][0].__setitem__(
                "type", "linkedmesh"
            ),
            lambda row: row["features"][0]["evidence"]["existing_tracks"][0]
            .__setitem__("property", "scale"),
        ]
        for mutate in cases:
            with self.subTest(mutate=mutate):
                self.assert_invalid(mutate)

    def test_all_evidence_collections_are_sorted_and_unique(self):
        collections = ("layers", "bindings", "bone_ids", "existing_tracks")
        for collection in collections:
            with self.subTest(collection=collection):
                self.assert_invalid(
                    lambda row, name=collection: row["features"][0]["evidence"][name]
                    .reverse()
                )
        self.assert_invalid(lambda row: row["features"][1]["reason_codes"].extend(
            ["z-reason", "a-reason"]
        ))
        self.assert_invalid(lambda row: row["features"][1]["reason_codes"].append(
            "manual-amplitude-required"
        ))

    def test_summary_is_finite_canonical_and_derived(self):
        cases = [
            lambda row: row["summary"].__setitem__("candidate_count", 2),
            lambda row: row["summary"].__setitem__("feature_count", 4.0),
            lambda row: row["summary"].__setitem__("unsupported_count", float("nan")),
            lambda row: row["summary"].__setitem__("extra", 0),
            lambda row: row["timing"].__setitem__("duration_ticks", float("inf")),
        ]
        for mutate in cases:
            with self.subTest(mutate=mutate):
                self.assert_invalid(mutate)

    def test_byte_limit_and_non_json_input_fail_closed(self):
        with patch(
            "autospine_workbench.idle_behavior_candidate_validation.MAX_DOCUMENT_BYTES",
            1,
        ):
            with self.assertRaises(IdleBehaviorCandidateValidationError):
                require_idle_behavior_candidates(valid_candidates())
        self.assert_invalid(lambda row: row.__setitem__("project_id", object()))
        with self.assertRaises(IdleBehaviorCandidateValidationError):
            require_idle_behavior_candidates(None)

    @unittest.skipIf(Draft202012Validator is None, "jsonschema is optional")
    def test_schema_parity_for_valid_and_structural_failures(self):
        schema = json.loads(
            (ROOT / "schemas" / "idle-behavior-candidates-v1.schema.json")
            .read_text(encoding="utf-8")
        )
        validator = Draft202012Validator(schema)
        validator.validate(valid_candidates())
        mutations = [
            lambda row: row["features"][1].__setitem__("candidate_id", None),
            lambda row: row["features"][0].__setitem__("availability", "candidate"),
            lambda row: row["features"][0]["evidence"]["layers"][0]
            .__setitem__("extra", True),
            lambda row: row["features"].reverse(),
        ]
        for mutate in mutations:
            document = valid_candidates()
            mutate(document)
            with self.subTest(mutate=mutate):
                with self.assertRaises(IdleBehaviorCandidateValidationError):
                    require_idle_behavior_candidates(document)
                self.assertTrue(tuple(validator.iter_errors(document)))


if __name__ == "__main__":
    unittest.main()
