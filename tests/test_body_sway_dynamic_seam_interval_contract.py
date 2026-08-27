"""Fail-closed contract tests for the P10.5d adaptive seam driver."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for item in (ROOT, SRC):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

import autospine_workbench.body_sway_dynamic_seam_interval \
    as driver  # noqa: E402
from autospine_workbench.body_sway_dynamic_seam_interval import (  # noqa: E402
    BodySwayDynamicSeamIntervalDriverError,
    prove_body_sway_dynamic_seam_sampled_linear_segment,
)
from autospine_workbench.body_sway_probe_geometry_context import (  # noqa: E402
    prepare_body_sway_geometry_context,
)
from tests.body_sway_dynamic_seam_interval_helpers import (  # noqa: E402
    dynamic_seam_driver_fixture,
    full_sample,
    interval_assessment,
)
from tests.body_sway_dynamic_seam_locator_helpers import (  # noqa: E402
    four_vertex_fixture,
)


class BodySwayDynamicSeamIntervalContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _rig, cls.context, cls.locators = dynamic_seam_driver_fixture()
        cls.left = full_sample(cls.context, tick=0)
        cls.right = full_sample(cls.context, tick=10)

    def prove(self, *, locators=None, context=None, left=None, right=None):
        return prove_body_sway_dynamic_seam_sampled_linear_segment(
            self.locators if locators is None else locators,
            self.context if context is None else context,
            self.left if left is None else left,
            self.right if right is None else right,
        )

    def test_cross_rig_and_endpoint_inventory_fail_closed(self):
        other_rig, other_target = four_vertex_fixture()
        other_context = prepare_body_sway_geometry_context(
            other_rig, other_target
        )
        with self.assertRaisesRegex(
            BodySwayDynamicSeamIntervalDriverError, "cross-wired",
        ):
            self.prove(
                context=other_context,
                left=full_sample(other_context, tick=0),
                right=full_sample(other_context, tick=1),
            )
        with self.assertRaisesRegex(
            BodySwayDynamicSeamIntervalDriverError, "ticks",
        ):
            self.prove(right=replace(self.right, tick=0))
        incomplete = replace(
            self.right,
            base_rotation_deg=self.right.base_rotation_deg[:-1],
            combined_rotation_deg=self.right.combined_rotation_deg[:-1],
        )
        with self.assertRaisesRegex(
            BodySwayDynamicSeamIntervalDriverError, "incomplete",
        ):
            self.prove(right=incomplete)

    def test_locator_and_backend_pair_inventory_drift_fail_closed(self):
        missing_relationship = replace(
            self.locators,
            relationships=self.locators.relationships[:-1],
        )
        with self.assertRaisesRegex(
            BodySwayDynamicSeamIntervalDriverError,
            "relationship inventory",
        ):
            self.prove(locators=missing_relationship)

        assessment = interval_assessment(self.locators)
        first = assessment.relationships[0]
        drifted = replace(
            assessment,
            relationships=(replace(
                first,
                pairs=first.pairs[:-1],
                max_squared_distance_upper_px2=0.5,
            ), *assessment.relationships[1:]),
            pair_count=assessment.pair_count - 1,
        )
        with patch.object(
            driver, "assess_body_sway_dynamic_seam_interval_box",
            return_value=drifted,
        ), self.assertRaisesRegex(
            BodySwayDynamicSeamIntervalDriverError, "pair evidence",
        ):
            self.prove()

    def test_forged_backend_semantics_fail_closed(self):
        valid = interval_assessment(self.locators)
        for forged in (
            replace(valid, common_root_translation_cancelled=False),
            replace(valid, distance_metric="forged-distance"),
            replace(
                valid,
                status="indeterminate",
                reason_codes=("forged_geometry_reason",),
            ),
        ):
            with self.subTest(forged=forged), patch.object(
                driver, "assess_body_sway_dynamic_seam_interval_box",
                return_value=forged,
            ), self.assertRaises(
                BodySwayDynamicSeamIntervalDriverError
            ):
                self.prove()

    def test_reported_upper_must_equal_delta_interval_recomputation(self):
        valid = interval_assessment(self.locators)
        relationship = valid.relationships[0]
        forged_pair = replace(
            relationship.pairs[0], squared_distance_upper_px2=0.0
        )
        forged_relationship = replace(
            relationship,
            pairs=(forged_pair, *relationship.pairs[1:]),
        )
        forged = replace(
            valid,
            relationships=(
                forged_relationship, *valid.relationships[1:]
            ),
        )
        with patch.object(
            driver, "assess_body_sway_dynamic_seam_interval_box",
            return_value=forged,
        ), self.assertRaisesRegex(
            BodySwayDynamicSeamIntervalDriverError, "squared upper",
        ):
            self.prove()


if __name__ == "__main__":
    unittest.main()
