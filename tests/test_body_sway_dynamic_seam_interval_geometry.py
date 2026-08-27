"""Focused outward interval geometry tests for P10.5d seam anchors."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
import math
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for item in (ROOT, SRC):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

import autospine_workbench.body_sway_dynamic_seam_interval_geometry \
    as interval_geometry  # noqa: E402
from autospine_workbench.body_sway_dynamic_seam_interval_geometry import (  # noqa: E402
    BodySwayDynamicSeamIntervalError,
    assess_body_sway_dynamic_seam_interval_box,
)
from autospine_workbench.body_sway_dynamic_seam_evidence_profile import (  # noqa: E402
    MAX_SQUARED_ANCHOR_GAP_PX2,
    THRESHOLD,
)
from autospine_workbench.body_sway_dynamic_seam_locator import (  # noqa: E402
    prepare_body_sway_dynamic_seam_locators,
    resolve_prepared_dynamic_seam_setup_exact,
)
from autospine_workbench.body_sway_interval_arithmetic import (  # noqa: E402
    ONE,
    OutwardInterval,
    ZERO,
)
from autospine_workbench.body_sway_probe_geometry_context import (  # noqa: E402
    prepare_body_sway_geometry_context,
)
from tests.body_sway_dynamic_seam_interval_helpers import (  # noqa: E402
    identical_locator_set,
    interval_pose,
    invalid_locator_inventories,
    overlapping_region_mesh_locators,
    point_matrices,
    project_locator,
)
from tests.body_sway_dynamic_seam_locator_helpers import (  # noqa: E402
    four_vertex_fixture,
    reviewed_set,
)
from tests.body_sway_probe_geometry_helpers import sample  # noqa: E402


class BodySwayDynamicSeamIntervalGeometryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rig, target = four_vertex_fixture()
        cls.context = prepare_body_sway_geometry_context(cls.rig, target)
        cls.locators = prepare_body_sway_dynamic_seam_locators(
            cls.rig, cls.context, reviewed_set(cls.rig)
        )
        cls.left = sample(
            base={"pelvis-spine": -2.0, "spine-chest": 1.0},
            overlay={
                "pelvis-spine": -8.0, "spine-chest": 4.0,
                "chest-neck": 2.0, "neck-head": -1.0,
            }, translation=(0.0, 0.0), tick=0,
        )
        cls.right = sample(
            base={"pelvis-spine": 3.0, "spine-chest": -2.0},
            overlay={
                "pelvis-spine": 7.0, "spine-chest": -3.0,
                "chest-neck": -2.5, "neck-head": 1.5,
            }, translation=(0.0, 0.0), tick=1,
        )

    def test_exact_identical_moments_leave_only_two_output_half_steps(self):
        locators = identical_locator_set(self.locators)
        result = assess_body_sway_dynamic_seam_interval_box(
            locators, self._pose()
        )
        pair = result.relationships[0].pairs[0]
        error = 1.0 / 4096.0

        self.assertEqual((-error, error), (
            pair.delta_x_px.lower, pair.delta_x_px.upper,
        ))
        self.assertEqual((-error, error), (
            pair.delta_y_px.lower, pair.delta_y_px.upper,
        ))
        self.assertLess(pair.squared_distance_upper_px2, 1e-6)
        self.assertEqual("certified", result.status)
        self.assertTrue(result.common_root_translation_cancelled)
        self.assertEqual("outward-squared-euclidean-no-sqrt",
                         result.distance_metric)
        self.assertEqual(6, result.relationship_count)
        self.assertEqual(12, result.pair_count)
        self.assertEqual(
            max(row.max_squared_distance_upper_px2
                for row in result.relationships),
            result.max_squared_distance_upper_px2,
        )

    def test_region_mesh_same_setup_has_zero_dense_gap_inside_bound(self):
        locators, context = overlapping_region_mesh_locators()
        pose = interval_pose(context, sample(tick=0), sample(tick=1))
        identity = (ONE, ZERO, ZERO, ONE, ZERO, ZERO)
        pose = replace(
            pose, skin_matrices=tuple(
                identity for _bone in context.skinning_rig._bones
            )
        )
        result = assess_body_sway_dynamic_seam_interval_box(locators, pose)
        source = locators.relationships[0].anchors[0]
        bound = result.relationships[0].pairs[0]

        self.assertEqual(
            resolve_prepared_dynamic_seam_setup_exact(source.parent),
            resolve_prepared_dynamic_seam_setup_exact(source.child),
        )
        self.assertLessEqual(bound.delta_x_px.lower, 0.0)
        self.assertGreaterEqual(bound.delta_x_px.upper, 0.0)
        self.assertLessEqual(bound.delta_y_px.lower, 0.0)
        self.assertGreaterEqual(bound.delta_y_px.upper, 0.0)
        self.assertGreaterEqual(bound.squared_distance_upper_px2, 0.0)

    def test_dense_dynamic_point_oracle_is_contained_without_sqrt(self):
        pose = self._pose()
        result = assess_body_sway_dynamic_seam_interval_box(
            self.locators, pose
        )
        for time in (0.0, 0.25, 0.5, 0.75, 1.0):
            for gain in (0.0, 0.25, 0.5, 0.75, 1.0):
                matrices = point_matrices(
                    self.context, self.left, self.right, time, gain
                )
                for relation, bounds in zip(
                    self.locators.relationships, result.relationships,
                    strict=True,
                ):
                    for pair, bound in zip(
                        relation.anchors, bounds.pairs, strict=True,
                    ):
                        parent = project_locator(pair.parent.moments, matrices)
                        child = project_locator(pair.child.moments, matrices)
                        dx, dy = child[0] - parent[0], child[1] - parent[1]
                        self.assertLessEqual(bound.delta_x_px.lower, dx)
                        self.assertGreaterEqual(bound.delta_x_px.upper, dx)
                        self.assertLessEqual(bound.delta_y_px.lower, dy)
                        self.assertGreaterEqual(bound.delta_y_px.upper, dy)
                        self.assertLessEqual(
                            dx * dx + dy * dy,
                            bound.squared_distance_upper_px2,
                        )

    def test_common_root_translation_is_cancelled_before_intervals(self):
        baseline = assess_body_sway_dynamic_seam_interval_box(
            self.locators, self._pose()
        )
        translated = assess_body_sway_dynamic_seam_interval_box(
            self.locators,
            self._pose(root=(900_000_000.0, -900_000_000.0)),
        )
        self.assertEqual(baseline, translated)

    def test_threshold_is_inclusive_and_next_float_is_unproven(self):
        locators = identical_locator_set(self.locators)
        pose = self._pose()
        seed = assess_body_sway_dynamic_seam_interval_box(locators, pose) \
            .relationships[0].pairs[0]
        cases = (
            (MAX_SQUARED_ANCHOR_GAP_PX2, "certified", ()),
            (
                math.nextafter(MAX_SQUARED_ANCHOR_GAP_PX2, math.inf),
                "indeterminate", ("anchor_proximity_unproven",),
            ),
        )
        for upper, status, reasons in cases:
            def forced(pair, _rig, _matrices):
                return replace(
                    seed, pair_id=pair.pair_id,
                    squared_distance_upper_px2=upper,
                )
            with self.subTest(upper=upper), patch.object(
                interval_geometry, "_pair_bound", side_effect=forced,
            ):
                result = assess_body_sway_dynamic_seam_interval_box(
                    locators, pose
                )
            self.assertEqual(status, result.status)
            self.assertEqual(reasons, result.reason_codes)
            self.assertEqual(MAX_SQUARED_ANCHOR_GAP_PX2,
                             result.threshold_squared_px2)
        self.assertEqual(
            MAX_SQUARED_ANCHOR_GAP_PX2,
            THRESHOLD["max_squared_anchor_gap_px2"],
        )
        with patch.object(
            interval_geometry, "MAX_SQUARED_ANCHOR_GAP_PX2", 3.0,
        ), patch.object(
            interval_geometry, "_pair_bound",
            side_effect=lambda pair, _rig, _matrices: replace(
                seed, pair_id=pair.pair_id,
                squared_distance_upper_px2=3.5,
            ),
        ):
            drift = assess_body_sway_dynamic_seam_interval_box(locators, pose)
        self.assertEqual(3.0, drift.threshold_squared_px2)
        self.assertEqual("indeterminate", drift.status)

    def test_real_fixture_outside_and_nonfinite_are_explicitly_unproven(self):
        outside = assess_body_sway_dynamic_seam_interval_box(
            self.locators, self._pose()
        )
        self.assertGreater(
            outside.max_squared_distance_upper_px2,
            MAX_SQUARED_ANCHOR_GAP_PX2,
        )
        self.assertIn("anchor_proximity_unproven", outside.reason_codes)

        whole = OutwardInterval(-math.inf, math.inf)
        nonfinite_pose = replace(
            self._pose(),
            skin_matrices=tuple(
                (whole,) * 6 for _bone in self.context.skinning_rig._bones
            ),
        )
        nonfinite = assess_body_sway_dynamic_seam_interval_box(
            self.locators, nonfinite_pose
        )
        self.assertEqual("indeterminate", nonfinite.status)
        self.assertIn("non_finite_interval_bound", nonfinite.reason_codes)
        self.assertTrue(math.isinf(
            nonfinite.max_squared_distance_upper_px2
        ))

    def test_fixed_inventory_and_finite_root_are_mandatory(self):
        for forged in invalid_locator_inventories(self.locators):
            with self.subTest(relationships=len(forged.relationships)), \
                    self.assertRaises(BodySwayDynamicSeamIntervalError):
                assess_body_sway_dynamic_seam_interval_box(
                    forged, self._pose()
                )
        whole = OutwardInterval(-math.inf, math.inf)
        forged_pose = replace(
            self._pose(), root_translation_xy=(whole, ZERO)
        )
        with self.assertRaisesRegex(
            BodySwayDynamicSeamIntervalError, "root translation",
        ):
            assess_body_sway_dynamic_seam_interval_box(
                self.locators, forged_pose
            )

    def test_crosswire_tamper_copy_and_frozen_results_fail_closed(self):
        other_rig, other_target = four_vertex_fixture()
        other_context = prepare_body_sway_geometry_context(
            other_rig, other_target
        )
        with self.assertRaisesRegex(
            BodySwayDynamicSeamIntervalError, "cross-wired",
        ):
            assess_body_sway_dynamic_seam_interval_box(
                self.locators,
                interval_pose(other_context, self.left, self.right),
            )

        relation = self.locators.relationships[0]
        pair = relation.anchors[0]
        forged_child = replace(pair.child, moments=pair.child.moments[:-1])
        forged_pair = replace(pair, child=forged_child)
        forged_anchors = (forged_pair,) + relation.anchors[1:]
        forged = replace(self.locators, relationships=(replace(
            relation, anchors=forged_anchors
        ),) + self.locators.relationships[1:])
        with self.assertRaises(BodySwayDynamicSeamIntervalError):
            assess_body_sway_dynamic_seam_interval_box(forged, self._pose())

        first = assess_body_sway_dynamic_seam_interval_box(
            self.locators, self._pose()
        )
        copied = deepcopy(first)
        self.assertEqual(first, copied)
        self.assertIsNot(first, copied)
        with self.assertRaises(FrozenInstanceError):
            first.status = "forged"  # type: ignore[misc]

    def _pose(self, *, root=(0.0, 0.0)):
        return interval_pose(
            self.context,
            replace(self.left, root_translation_xy=root),
            replace(self.right, root_translation_xy=root),
        )


if __name__ == "__main__":
    unittest.main()
