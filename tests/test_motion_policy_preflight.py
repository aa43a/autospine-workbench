"""Pure contracts for the zero-write P9 preflight compiler."""

from __future__ import annotations

from copy import deepcopy
import json
import unittest

from tests.motion_policy_preflight_helpers import MotionPolicyFixtureMixin

from autospine_workbench.depth_pair_policy import depth_pair_policy_sha256
from autospine_workbench.motion_policy_candidate_inventory import (
    motion_policy_candidate_ids_sha256,
)
from autospine_workbench.motion_policy_preflight import (
    CANDIDATE_INVENTORY,
    POLICY_IDENTITY,
    REQUEST_FORMAT,
    RESULT_FORMAT,
    MotionPolicyPreflightError,
    _cross_policy_depth,
    compile_motion_policy_preflight,
)


class MotionPolicyPreflightTests(
    MotionPolicyFixtureMixin,
    unittest.TestCase,
):
    def test_policy_identity_uses_python_number_semantics(self) -> None:
        floating = deepcopy(self.policy)
        floating["hysteresis"]["enter_threshold"] = 1.0
        integer = deepcopy(floating)
        integer["hysteresis"]["enter_threshold"] = 1
        float_result = compile_motion_policy_preflight(
            self._policy_request(floating)
        )
        int_result = compile_motion_policy_preflight(
            self._policy_request(integer)
        )
        self.assertEqual(
            depth_pair_policy_sha256(floating),
            float_result["identities"]["policy_sha256"],
        )
        self.assertEqual(
            depth_pair_policy_sha256(integer),
            int_result["identities"]["policy_sha256"],
        )
        self.assertNotEqual(
            float_result["identities"]["policy_sha256"],
            int_result["identities"]["policy_sha256"],
        )

        scientific = deepcopy(self.policy)
        scientific["hysteresis"].update(
            enter_threshold=1e-6,
            exit_threshold=1e-7,
        )
        raw = self._json(scientific)
        self.assertIn("1e-06", raw)
        self.assertIn("1e-07", raw)
        result = compile_motion_policy_preflight({
            "format": REQUEST_FORMAT,
            "format_version": 1,
            "operation": POLICY_IDENTITY,
            "policy_json": raw,
        })
        self.assertEqual(
            depth_pair_policy_sha256(scientific),
            result["identities"]["policy_sha256"],
        )

        valid_raw = self._json(self.policy)
        duplicate = valid_raw.replace(
            '"format":',
            '"format":"autospine-depth-pair-policy","format":',
            1,
        )
        nonfinite = valid_raw.replace("0.05", "NaN", 1)
        for invalid_raw in (duplicate, nonfinite):
            with self.subTest(invalid=invalid_raw[:20]), \
                    self.assertRaises(MotionPolicyPreflightError):
                compile_motion_policy_preflight({
                    "format": REQUEST_FORMAT,
                    "format_version": 1,
                    "operation": POLICY_IDENTITY,
                    "policy_json": invalid_raw,
                })

    def test_candidate_id_inventory_digest_matches_browser_golden(self):
        ids = [f'depth-{"2" * 64}', f'foot-{"1" * 64}']
        self.assertEqual(
            "bc5886cb0e49487b2fae31f4305b391630299d2602d77463bee0606f11049982",
            motion_policy_candidate_ids_sha256(ids),
        )
        self.assertEqual(
            motion_policy_candidate_ids_sha256(ids),
            motion_policy_candidate_ids_sha256(reversed(ids)),
        )

    def test_candidate_inventory_binds_all_three_canonical_identities(self):
        request = self._candidate_request()
        result = compile_motion_policy_preflight(request)
        self.assertEqual({
            "format", "format_version", "status", "operation",
            "project_id", "clip_id", "identities", "inventory",
        }, set(result))
        self.assertEqual(RESULT_FORMAT, result["format"])
        self.assertEqual(CANDIDATE_INVENTORY, result["operation"])
        self.assertEqual(request["declared"], result["identities"])
        counts = result["inventory"]
        self.assertEqual(
            counts["total_count"],
            counts["foot_count"] + counts["depth_count"],
        )
        self.assertGreater(counts["total_count"], 0)
        self.assertRegex(counts["candidate_ids_sha256"], r"^[0-9a-f]{64}$")

        float_index = self._candidate_request()
        foot = deepcopy(self.foot)
        foot["samples"][0]["source_frame_index"] = 0.0
        float_index["foot_candidates_json"] = self._json(foot)
        with self.assertRaises(MotionPolicyPreflightError):
            compile_motion_policy_preflight(float_index)

        envelope = deepcopy(request)
        envelope["foot_candidates_json"] = self._json({
            "input_bundle_paths": [r"C:\private\p8", r"C:\private\p5"],
            "report_sha256": request["declared"][
                "foot_candidates_sha256"
            ],
            "report": self.foot,
            "ok": True,
            "status": "passed",
        })
        encoded = self._json(compile_motion_policy_preflight(envelope))
        self.assertNotIn("private", encoded)
        ambiguous = deepcopy(envelope)
        wrapper = json.loads(ambiguous["foot_candidates_json"])
        wrapper["latest"] = True
        ambiguous["foot_candidates_json"] = self._json(wrapper)
        with self.assertRaises(MotionPolicyPreflightError):
            compile_motion_policy_preflight(ambiguous)

    def test_stale_arbitrary_incomplete_and_crosswired_inputs_fail(self):
        stale = self._candidate_request()
        tampered_foot = deepcopy(self.foot)
        tampered_foot["source"]["camera_sha256"] = "f" * 64
        stale["foot_candidates_json"] = self._json(tampered_foot)
        with self.assertRaises(MotionPolicyPreflightError):
            compile_motion_policy_preflight(stale)

        stale_envelope = self._candidate_request()
        stale_envelope["foot_candidates_json"] = self._json({
            "input_bundle_paths": ["p8", "p5"],
            "report_sha256": stale_envelope["declared"][
                "foot_candidates_sha256"
            ],
            "report": tampered_foot,
            "ok": True,
            "status": "passed",
        })
        with self.assertRaises(MotionPolicyPreflightError):
            compile_motion_policy_preflight(stale_envelope)

        arbitrary = self._candidate_request()
        arbitrary["declared"]["foot_candidates_sha256"] = "f" * 64
        with self.assertRaises(MotionPolicyPreflightError):
            compile_motion_policy_preflight(arbitrary)

        incomplete = self._candidate_request()
        foot = deepcopy(self.foot)
        del foot["summary"]
        incomplete["foot_candidates_json"] = self._json(foot)
        with self.assertRaises(MotionPolicyPreflightError):
            compile_motion_policy_preflight(incomplete)

        mismatched = self._candidate_request()
        policy = deepcopy(self.policy)
        policy["hysteresis"]["enter_threshold"] = 0.06
        mismatched["policy_json"] = self._json(policy)
        mismatched["declared"]["policy_sha256"] = (
            depth_pair_policy_sha256(policy)
        )
        with self.assertRaises(MotionPolicyPreflightError):
            compile_motion_policy_preflight(mismatched)

        for field, policy_value, depth_value in (
            ("exit_threshold", 0, -0.0),
            ("enter_threshold", 1, 1.0),
        ):
            with self.subTest(exact_hysteresis=field):
                policy = deepcopy(self.policy)
                depth = deepcopy(self.depth)
                policy["hysteresis"][field] = policy_value
                depth["hysteresis"][field] = depth_value
                policy_sha = depth_pair_policy_sha256(policy)
                depth["source"]["depth_pair_policy_sha256"] = policy_sha
                with self.assertRaises(MotionPolicyPreflightError):
                    _cross_policy_depth(policy, depth, policy_sha)


if __name__ == "__main__":
    unittest.main()
