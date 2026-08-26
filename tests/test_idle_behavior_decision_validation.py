"""Standalone, semantic, and schema tests for IdleBehaviorDecision v1."""

from __future__ import annotations

from copy import deepcopy
import json
import math
from pathlib import Path
import unittest
from unittest.mock import patch

from autospine_workbench.idle_behavior_decision import (
    build_idle_behavior_decision,
)
from autospine_workbench.idle_behavior_decision_validation import (
    IdleBehaviorDecisionValidationError,
    require_idle_behavior_decision,
)
from tests.idle_behavior_decision_helpers import (
    adjust_decision,
    candidates_without_candidate,
    completed_review,
    terminal_decision,
)
from tests.test_idle_behavior_candidate_validation import valid_candidates

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover - optional test dependency
    Draft202012Validator = None


ROOT = Path(__file__).resolve().parents[1]


def valid_decision(candidates=None, decisions=None):
    selected = valid_candidates() if candidates is None else candidates
    rows = [adjust_decision(selected)] if decisions is None else decisions
    return build_idle_behavior_decision(
        selected, review=completed_review(), decisions=rows,
    ).document


class IdleBehaviorDecisionValidationTests(unittest.TestCase):
    def assert_standalone_invalid(self, mutate):
        document = valid_decision()
        mutate(document)
        with self.assertRaises(IdleBehaviorDecisionValidationError):
            require_idle_behavior_decision(document)

    def test_top_source_timing_semantics_and_summary_are_exact(self):
        mutations = (
            lambda row: row.__setitem__("extra", True),
            lambda row: row["source"].__setitem__("extra", "a" * 64),
            lambda row: row["source"].pop("target_profile_sha256"),
            lambda row: row["source"].__setitem__(
                "motion_instance_v2_sha256", "A" * 64
            ),
            lambda row: row["timing"].__setitem__("loop", 1),
            lambda row: row["timing"].__setitem__("duration_ticks", 0),
            lambda row: row["semantics"].__setitem__(
                "runtime_timeline_emitted", True
            ),
            lambda row: row["semantics"].__setitem__(
                "safe_range_claimed", True
            ),
            lambda row: row["semantics"].__setitem__(
                "automatic_acceptance", True
            ),
            lambda row: row["summary"].__setitem__("adjust_count", 0),
            lambda row: row["summary"].__setitem__("decision_count", 1.0),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                self.assert_standalone_invalid(mutate)

    def test_missing_duplicate_extra_and_unsorted_decisions_fail_closed(self):
        candidates = valid_candidates()
        baseline = valid_decision(candidates)
        missing = deepcopy(baseline)
        missing["decisions"] = []
        missing["summary"] = {
            key: 0 for key in missing["summary"]
        }
        with self.assertRaisesRegex(
            IdleBehaviorDecisionValidationError, "not exhaustive"
        ):
            require_idle_behavior_decision(missing, candidates=candidates)

        duplicate = deepcopy(baseline)
        duplicate["decisions"].append(deepcopy(duplicate["decisions"][0]))
        duplicate["summary"].update({
            "candidate_count": 2, "decision_count": 2, "adjust_count": 2,
            "pending_probe_count": 2,
        })
        with self.assertRaises(IdleBehaviorDecisionValidationError):
            require_idle_behavior_decision(duplicate)

        extra_row = terminal_decision("reject", candidates)
        original = baseline["decisions"][0]["candidate_id"]
        extra_row["candidate_id"] = (
            "body-sway-" + ("f" if original[-64:] != "f" * 64 else "0") * 64
        )
        extra = deepcopy(baseline)
        extra["decisions"] = sorted(
            [extra["decisions"][0], extra_row], key=lambda row: row["candidate_id"]
        )
        extra["summary"].update({
            "candidate_count": 2, "decision_count": 2, "reject_count": 1,
        })
        with self.assertRaisesRegex(
            IdleBehaviorDecisionValidationError, "not exhaustive"
        ):
            require_idle_behavior_decision(extra, candidates=candidates)
        extra["decisions"].reverse()
        with self.assertRaisesRegex(
            IdleBehaviorDecisionValidationError, "sorted"
        ):
            require_idle_behavior_decision(extra)

    def test_stale_sha_id_project_clip_timing_and_copied_sources_fail(self):
        candidates = valid_candidates()
        baseline = valid_decision(candidates)
        mutations = (
            lambda row: row["source"].__setitem__(
                "idle_behavior_candidates_sha256", "0" * 64
            ),
            lambda row: row["source"].__setitem__(
                "target_profile_sha256", "0" * 64
            ),
            lambda row: row["source"].__setitem__(
                "motion_instance_v2_sha256", "0" * 64
            ),
            lambda row: row["source"].__setitem__(
                "reviewed_motion_bundle_sha256", "0" * 64
            ),
            lambda row: row["decisions"][0].__setitem__(
                "candidate_id", "body-sway-" + "0" * 64
            ),
            lambda row: row.__setitem__("project_id", "other.project"),
            lambda row: row.__setitem__("clip_id", "other-clip"),
            lambda row: row["timing"].__setitem__("loop", False),
        )
        for mutate in mutations:
            changed = deepcopy(baseline)
            mutate(changed)
            with self.subTest(mutate=mutate), self.assertRaises(
                IdleBehaviorDecisionValidationError
            ):
                require_idle_behavior_decision(changed, candidates=candidates)

    def test_action_payload_and_probe_status_are_conditional(self):
        mutations = (
            lambda row: row["decisions"][0].__setitem__("action", "accept"),
            lambda row: row["decisions"][0].__setitem__("payload", None),
            lambda row: row["decisions"][0].__setitem__(
                "probe_status", "not_applicable"
            ),
            lambda row: row["decisions"][0]["payload"].__setitem__("extra", 1),
            lambda row: row["decisions"][0].__setitem__("feature_id", "blink"),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                self.assert_standalone_invalid(mutate)
        for action in ("reject", "unobservable"):
            document = valid_decision(decisions=[terminal_decision(action)])
            for field, value in (
                ("payload", {}), ("probe_status", "pending_probe")
            ):
                changed = deepcopy(document)
                changed["decisions"][0][field] = value
                with self.subTest(action=action, field=field), self.assertRaises(
                    IdleBehaviorDecisionValidationError
                ):
                    require_idle_behavior_decision(changed)

    def test_numeric_bounds_and_nonfinite_values_fail_closed(self):
        cases = (
            ("cycles", 0), ("cycles", 65), ("cycles", 1.0),
            ("cycles", True),
            ("amplitude", -0.01), ("amplitude", 10.01),
            ("amplitude", float("nan")), ("amplitude", float("inf")),
            ("amplitude", True),
            ("phase", -0.01), ("phase", 1.0),
            ("phase", float("nan")), ("phase", float("inf")),
        )
        for field, value in cases:
            document = valid_decision()
            payload = document["decisions"][0]["payload"]
            if field == "cycles":
                payload["cycles"] = value
            elif field == "amplitude":
                payload["per_bone_amplitude_deg"][0]["value"] = value
            else:
                payload["per_bone_phase_fraction"][0]["value"] = value
            with self.subTest(field=field, value=value), self.assertRaises(
                IdleBehaviorDecisionValidationError
            ):
                require_idle_behavior_decision(document)
        all_zero = valid_decision()
        for row in all_zero["decisions"][0]["payload"][
            "per_bone_amplitude_deg"
        ]:
            row["value"] = 0
        with self.assertRaisesRegex(
            IdleBehaviorDecisionValidationError, "non-zero"
        ):
            require_idle_behavior_decision(all_zero)

    def test_numeric_boundaries_are_allowed(self):
        document = valid_decision()
        payload = document["decisions"][0]["payload"]
        payload["cycles"] = 64
        payload["per_bone_amplitude_deg"][0]["value"] = 10
        payload["per_bone_amplitude_deg"][-1]["value"] = 0
        payload["per_bone_phase_fraction"][0]["value"] = 0
        payload["per_bone_phase_fraction"][-1]["value"] = math.nextafter(1.0, 0.0)
        require_idle_behavior_decision(document, candidates=valid_candidates())

    def test_per_bone_inventory_must_match_and_follow_proposal_order(self):
        baseline = valid_decision()
        payload = baseline["decisions"][0]["payload"]
        mismatch = deepcopy(baseline)
        mismatch["decisions"][0]["payload"][
            "per_bone_phase_fraction"
        ].pop()
        with self.assertRaisesRegex(
            IdleBehaviorDecisionValidationError, "inventories differ"
        ):
            require_idle_behavior_decision(mismatch)
        duplicate = deepcopy(baseline)
        rows = duplicate["decisions"][0]["payload"][
            "per_bone_amplitude_deg"
        ]
        rows[1]["bone_id"] = rows[0]["bone_id"]
        with self.assertRaisesRegex(
            IdleBehaviorDecisionValidationError, "unique"
        ):
            require_idle_behavior_decision(duplicate)
        reordered = deepcopy(baseline)
        for field in ("per_bone_amplitude_deg", "per_bone_phase_fraction"):
            reordered["decisions"][0]["payload"][field].reverse()
        require_idle_behavior_decision(reordered)
        with self.assertRaisesRegex(
            IdleBehaviorDecisionValidationError, "bone order"
        ):
            require_idle_behavior_decision(
                reordered, candidates=valid_candidates()
            )
        self.assertEqual(4, len(payload["per_bone_amplitude_deg"]))

    def test_byte_limit_and_non_mapping_input_fail_closed(self):
        document = valid_decision()
        with patch(
            "autospine_workbench.idle_behavior_decision_validation.MAX_DOCUMENT_BYTES",
            1,
        ):
            with self.assertRaisesRegex(
                IdleBehaviorDecisionValidationError, "byte limit"
            ):
                require_idle_behavior_decision(document)
        with self.assertRaises(IdleBehaviorDecisionValidationError):
            require_idle_behavior_decision(None)

    @unittest.skipIf(Draft202012Validator is None, "jsonschema is optional")
    def test_schema_matches_valid_adjust_reject_and_empty_documents(self):
        schema = json.loads((
            ROOT / "schemas" / "idle-behavior-decision-v1.schema.json"
        ).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        documents = [
            valid_decision(),
            valid_decision(decisions=[terminal_decision("reject")]),
            valid_decision(candidates_without_candidate(), decisions=[]),
        ]
        for document in documents:
            validator.validate(document)
        mutations = (
            lambda row: row["decisions"][0].__setitem__("action", "accept"),
            lambda row: row["decisions"][0].__setitem__("payload", None),
            lambda row: row["semantics"].__setitem__("safe_range_claimed", True),
            lambda row: row["source"].__setitem__("extra", "a" * 64),
        )
        for mutate in mutations:
            document = valid_decision()
            mutate(document)
            with self.subTest(mutate=mutate):
                self.assertTrue(tuple(validator.iter_errors(document)))


if __name__ == "__main__":
    unittest.main()
