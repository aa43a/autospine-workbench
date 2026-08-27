"""Semantic hardening tests for P10.5d segment backend admission."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for item in (ROOT, SRC):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from autospine_workbench.body_sway_dynamic_seam_backend_validation import (  # noqa: E402
    BodySwayDynamicSeamBackendValidationError,
    require_body_sway_dynamic_seam_interval_result,
)
from autospine_workbench.body_sway_dynamic_seam_interval import (  # noqa: E402
    BodySwayDynamicSeamIntervalBudget,
)
from tests.body_sway_dynamic_seam_analysis_helpers import (  # noqa: E402
    certified_proof,
)
from tests.body_sway_dynamic_seam_interval_helpers import (  # noqa: E402
    dynamic_seam_driver_fixture,
)


class BodySwayDynamicSeamBackendValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _rig, _context, cls.locators = dynamic_seam_driver_fixture()
        cls.budget = BodySwayDynamicSeamIntervalBudget()

    def require(self, proof):
        return require_body_sway_dynamic_seam_interval_result(
            proof, locator_set=self.locators,
            left_tick=0, right_tick=1, budget=self.budget,
        )

    def test_certified_and_consistent_indeterminate_results_are_admitted(self):
        seed = certified_proof(self.locators, 0, 1)
        outside = _indeterminate(
            seed, 5.0,
            ("anchor_proximity_unproven",
             "subdivision_depth_exhausted"),
        )
        unbounded = _indeterminate(
            seed, None,
            ("anchor_proximity_unproven", "non_finite_interval_bound",
             "subdivision_depth_exhausted"),
        )
        self.assertEqual(
            "continuous_anchor_proximity_certified",
            self.require(seed)["status"],
        )
        self.assertEqual("indeterminate", self.require(outside)["status"])
        self.assertIsNone(
            self.require(unbounded)["max_squared_distance_upper_px2"]
        )

    def test_tree_reasons_bounds_ticks_and_fixed_semantics_cannot_be_forged(self):
        seed = certified_proof(self.locators, 0, 1)
        attacks = (
            replace(seed, evaluated_box_count=3),
            _indeterminate(seed, 0.5, ("invented",)),
            replace(seed, left_tick=9),
            replace(seed, time_model="point-sampled"),
            _indeterminate(seed, 0.5,
                           ("subdivision_depth_exhausted",)),
            _indeterminate(
                seed, None,
                ("anchor_proximity_unproven",
                 "subdivision_depth_exhausted"),
            ),
            _indeterminate(
                seed, 0.5,
                ("anchor_proximity_unproven",
                 "subdivision_depth_exhausted"),
            ),
            _indeterminate(
                seed, 5.0,
                ("non_finite_interval_bound",
                 "subdivision_depth_exhausted"),
            ),
        )
        for proof in attacks:
            with self.subTest(proof=proof), self.assertRaises(
                BodySwayDynamicSeamBackendValidationError
            ):
                self.require(proof)


def _indeterminate(seed, value, reasons):
    return replace(
        _with_all_pair_maxima(seed, value),
        status="indeterminate", reason_codes=tuple(sorted(reasons)),
        certified_terminal_box_count=0,
        indeterminate_terminal_box_count=1,
    )


def _with_all_pair_maxima(proof, value):
    relationships = tuple(
        replace(
            relationship,
            pairs=tuple(replace(
                pair, max_squared_distance_upper_px2=value,
            ) for pair in relationship.pairs),
            max_squared_distance_upper_px2=value,
        ) for relationship in proof.relationships
    )
    return replace(
        proof, relationships=relationships,
        max_squared_distance_upper_px2=value,
    )


if __name__ == "__main__":
    unittest.main()
