"""Pinned semantics tests for the P10.5d dynamic seam result layer."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for item in (ROOT, SRC):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from autospine_workbench.body_sway_continuous_proof_profile import (  # noqa: E402
    GAIN_DOMAIN,
    INTERPOLATION,
    body_sway_continuous_proof_problem,
)
from autospine_workbench.body_sway_dynamic_seam_evidence_profile import (  # noqa: E402
    BUDGET,
    INVENTORY_HASH_DOMAIN,
    MAX_SQUARED_ANCHOR_GAP_PX2,
    body_sway_dynamic_seam_analyzer_profile,
    body_sway_dynamic_seam_claims,
    body_sway_dynamic_seam_problem,
    body_sway_dynamic_seam_problem_sha256,
    body_sway_dynamic_seam_release_gate,
    body_sway_dynamic_seam_segment_sha256,
)
from autospine_workbench.resolved_project import canonical_sha256  # noqa: E402
from autospine_workbench.reviewed_seam_anchor_set_compiler import (  # noqa: E402
    compile_reviewed_seam_anchor_set,
)
from tests.reviewed_seam_anchor_set_helpers import reviewed_set_inputs  # noqa: E402


SOURCE_SHA = "a" * 64
TICKS = [0, 6, 12]


def compiled_set(*, mesh=False):
    candidate, decision, rig = reviewed_set_inputs(
        mesh_id="arm.left" if mesh else None
    )
    return compile_reviewed_seam_anchor_set(
        candidate, decision, rig
    ).document


class BodySwayDynamicSeamEvidenceProfileTests(unittest.TestCase):
    def test_metric_is_explicit_engineering_proxy_with_fixed_budget(self):
        config = body_sway_dynamic_seam_analyzer_profile()["config"]
        threshold = config["threshold"]
        self.assertEqual(4.0, MAX_SQUARED_ANCHOR_GAP_PX2)
        self.assertEqual(4.0, threshold["max_squared_anchor_gap_px2"])
        self.assertEqual(2.0, threshold["equivalent_anchor_gap_px"])
        self.assertIn("engineering-proxy", threshold["interpretation"])
        self.assertIn("not-visual-calibration", threshold["interpretation"])
        self.assertEqual({
            "max_depth": 14,
            "max_boxes_per_segment": 32768,
            "max_total_boxes": 32768,
        }, BUDGET)
        self.assertEqual(BUDGET, config["budget"])
        self.assertIn("q65535", config["backend"]["locator_enclosure"])
        self.assertIn("common-root-cancelled", config["backend"]["anchor_pose"])
        self.assertIn("no-square-root", config["backend"]["distance_bound"])
        self.assertIn("full-attachment-boundary-continuity", config[
            "exclusions"
        ])

    def test_problem_reuses_exact_p10_4b2_time_and_gain_domains(self):
        reviewed = compiled_set()
        dynamic = body_sway_dynamic_seam_problem(
            SOURCE_SHA, TICKS, reviewed
        )
        continuous = body_sway_continuous_proof_problem(SOURCE_SHA, TICKS)
        self.assertEqual(GAIN_DOMAIN, dynamic["gain_domain"])
        self.assertEqual(INTERPOLATION, dynamic["interpolation"])
        self.assertEqual(continuous["gain_domain"], dynamic["gain_domain"])
        self.assertEqual(continuous["time_domain"], dynamic["time_domain"])
        self.assertEqual(
            continuous["interpolation"], dynamic["interpolation"]
        )

    def test_problem_binds_six_relationships_and_every_pair(self):
        reviewed = compiled_set(mesh=True)
        problem = body_sway_dynamic_seam_problem(
            SOURCE_SHA, TICKS, reviewed
        )
        inventory = problem["reviewed_anchor_inventory"]
        relationships = reviewed["relationships"]
        self.assertEqual(6, inventory["relationship_count"])
        self.assertEqual(
            sum(len(row["anchors"]) for row in relationships),
            inventory["anchor_pair_count"],
        )
        self.assertEqual(canonical_sha256({
            "domain": INVENTORY_HASH_DOMAIN,
            "relationships": relationships,
        }), inventory["reviewed_anchor_inventory_sha256"])
        self.assertEqual(
            problem["problem_sha256"],
            body_sway_dynamic_seam_problem_sha256(problem),
        )

    def test_profile_problem_and_hashes_are_copy_isolated_deterministic(self):
        reviewed = compiled_set()
        first = body_sway_dynamic_seam_problem(SOURCE_SHA, TICKS, reviewed)
        second = body_sway_dynamic_seam_problem(SOURCE_SHA, TICKS, reviewed)
        self.assertEqual(first, second)
        first["gain_domain"]["closure"] = "open"
        self.assertEqual("closed", second["gain_domain"]["closure"])
        profile = body_sway_dynamic_seam_analyzer_profile()
        profile["config"]["budget"]["max_depth"] = 1
        self.assertEqual(
            14,
            body_sway_dynamic_seam_analyzer_profile()["config"]
                ["budget"]["max_depth"],
        )
        segment = {"left_tick": 0, "right_tick": 6, "status": "certified"}
        digest = body_sway_dynamic_seam_segment_sha256(segment)
        sealed = {**segment, "segment_evidence_sha256": digest}
        self.assertEqual(digest, body_sway_dynamic_seam_segment_sha256(sealed))
        changed = {**sealed, "right_tick": 7}
        self.assertNotEqual(digest, body_sway_dynamic_seam_segment_sha256(changed))

    def test_claims_are_narrow_and_release_is_always_blocked(self):
        expected_fields = {
            "reviewed_seam_anchor_set_bound",
            "continuous_preview_model_reviewed_anchor_proximity_within_"
            "engineering_tolerance",
            "dynamic_seam_safety", "visual_seam_quality",
            "runtime_equivalence", "publishable_timeline",
            "release_authority",
        }
        for certified in (False, True):
            claims = body_sway_dynamic_seam_claims(certified)
            self.assertEqual(expected_fields, set(claims))
            self.assertTrue(claims["reviewed_seam_anchor_set_bound"])
            conditional = [
                key for key, value in claims.items()
                if value and key != "reviewed_seam_anchor_set_bound"
            ]
            self.assertEqual(
                ["continuous_preview_model_reviewed_anchor_proximity_within_"
                 "engineering_tolerance"] if certified else [],
                conditional,
            )
            self.assertEqual(
                "blocked",
                body_sway_dynamic_seam_release_gate(certified)["status"],
            )
        rejected = body_sway_dynamic_seam_release_gate(False)["reason_codes"]
        certified = body_sway_dynamic_seam_release_gate(True)["reason_codes"]
        self.assertIn(
            "continuous_preview_model_reviewed_anchor_proximity_unproven",
            rejected,
        )
        self.assertIn("unit_gain_interval_unproven", rejected)
        self.assertNotIn(
            "continuous_preview_model_reviewed_anchor_proximity_unproven",
            certified,
        )
        self.assertIn("visual_seam_quality_unproven", certified)

    def test_malformed_inputs_nonfinite_and_resealed_tamper_fail(self):
        reviewed = compiled_set()
        class Text(str):
            pass

        class Ticks(list):
            pass

        attacks = (
            ("A" * 64, TICKS, reviewed),
            (SOURCE_SHA, (0, 6), reviewed),
            (Text(SOURCE_SHA), TICKS, reviewed),
            (SOURCE_SHA, Ticks(TICKS), reviewed),
            (SOURCE_SHA, [0, True], reviewed),
            (SOURCE_SHA, [0, 0], reviewed),
            (SOURCE_SHA, TICKS, []),
        )
        for source_sha, ticks, value in attacks:
            with self.subTest(value=(source_sha, ticks)), \
                    self.assertRaises(ValueError):
                body_sway_dynamic_seam_problem(source_sha, ticks, value)
        nonfinite = deepcopy(reviewed)
        nonfinite["relationships"][0]["anchors"][0]["parent"] \
            ["local_xy_q4096"][0] = float("nan")
        with self.assertRaises(ValueError):
            body_sway_dynamic_seam_problem(SOURCE_SHA, TICKS, nonfinite)
        tampered = deepcopy(reviewed)
        tampered["relationships"][0]["anchors"][0]["pair_id"] = "anchor.999"
        with self.assertRaises(ValueError):
            body_sway_dynamic_seam_problem(SOURCE_SHA, TICKS, tampered)
        with self.assertRaises(ValueError):
            body_sway_dynamic_seam_problem_sha256([])
        with self.assertRaises(ValueError):
            body_sway_dynamic_seam_segment_sha256({"value": float("inf")})
        for invalid in (0, 1, None, "true"):
            with self.assertRaises(ValueError):
                body_sway_dynamic_seam_claims(invalid)
            with self.assertRaises(ValueError):
                body_sway_dynamic_seam_release_gate(invalid)


if __name__ == "__main__":
    unittest.main()
