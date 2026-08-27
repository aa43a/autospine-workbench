"""High-level fail-closed analysis/compiler tests for P10.5d."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for item in (ROOT, SRC):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from autospine_workbench.body_sway_dynamic_seam import (  # noqa: E402
    FORMAT,
    FORMAT_VERSION,
    compile_body_sway_dynamic_seam_probe,
)
from autospine_workbench.body_sway_dynamic_seam_analysis import (  # noqa: E402
    CERTIFIED_STATUS,
    analyze_body_sway_dynamic_seam_source,
)
from autospine_workbench.body_sway_dynamic_seam_evidence_profile import (  # noqa: E402
    MAX_TOTAL_BOXES,
    body_sway_dynamic_seam_segment_sha256,
)
from tests.body_sway_dynamic_seam_analysis_helpers import (  # noqa: E402
    admitted_source,
    certified_proof,
    patched_pipeline,
)
from tests.body_sway_dynamic_seam_interval_helpers import (  # noqa: E402
    dynamic_seam_driver_fixture,
)


class BodySwayDynamicSeamAnalysisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rig, cls.context, cls.locators = dynamic_seam_driver_fixture()

    def _certified_driver(self, _locators, _context, left, right, *, budget):
        return certified_proof(
            self.locators, left.tick, right.tick,
            boxes=min(1, budget.max_boxes),
        )

    def test_deterministic_full_adjacent_coverage_and_segment_seals(self):
        source = admitted_source(self.rig, ticks=(0, 2, 5, 9))
        calls = []

        def driver(_locators, _context, left, right, *, budget):
            calls.append((left.tick, right.tick, budget.max_boxes))
            return certified_proof(self.locators, left.tick, right.tick)

        with patched_pipeline(
            source, self.context, self.locators, driver=driver,
        ):
            first = analyze_body_sway_dynamic_seam_source(source)
            second = analyze_body_sway_dynamic_seam_source(source)
        self.assertEqual(first.canonical_bytes, second.canonical_bytes)
        self.assertEqual(first.sha256, second.sha256)
        self.assertEqual(
            [(0, 2), (2, 5), (5, 9)],
            [(row["left_tick"], row["right_tick"])
             for row in first.document["segments"]],
        )
        self.assertEqual(6, first.document["summary"]["relationship_count"])
        self.assertEqual(6, len(first.document["segments"][0][
            "relationships"
        ]))
        for row in first.document["segments"]:
            self.assertEqual(
                row["segment_evidence_sha256"],
                body_sway_dynamic_seam_segment_sha256(row),
            )
        self.assertEqual(6, len(calls))

    def test_global_box_budget_stops_later_driver_calls(self):
        source = admitted_source(self.rig, ticks=(0, 1, 2, 3))

        def consume_budget(_locators, _context, left, right, *, budget):
            boxes = budget.max_boxes if budget.max_boxes % 2 else (
                budget.max_boxes - 1
            )
            return certified_proof(
                self.locators, left.tick, right.tick,
                boxes=boxes, depth=14 if boxes > 1 else 0,
            )

        with patched_pipeline(
            source, self.context, self.locators, driver=consume_budget,
        ) as (_source, _compiler, driver):
            document = analyze_body_sway_dynamic_seam_source(source).document
        self.assertEqual(2, driver.call_count)
        self.assertEqual(MAX_TOTAL_BOXES,
                         document["summary"]["evaluated_box_count"])
        self.assertEqual(
            ["continuous_anchor_proximity_certified",
             "continuous_anchor_proximity_certified", "indeterminate"],
            [row["status"] for row in document["segments"]],
        )
        for row in document["segments"][2:]:
            self.assertEqual(
                ["global_subdivision_box_budget_exhausted"],
                row["reason_codes"],
            )
            self._assert_complete_unknown_inventory(row)

    def test_backend_exception_and_wrong_type_fail_closed(self):
        source = admitted_source(self.rig, ticks=(0, 1, 2))
        for backend in (
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                RuntimeError("backend exploded")
            ),
            lambda *_args, **_kwargs: {"status": "certified"},
        ):
            with self.subTest(backend=backend), patched_pipeline(
                source, self.context, self.locators, driver=backend,
            ) as (_source, _compiler, driver):
                document = analyze_body_sway_dynamic_seam_source(
                    source
                ).document
            self.assertEqual(1, driver.call_count)
            self.assertEqual("indeterminate", document["status"])
            self.assertEqual(
                ["interval_backend_error"],
                document["segments"][0]["reason_codes"],
            )
            self.assertEqual(
                ["global_subdivision_box_budget_exhausted"],
                document["segments"][1]["reason_codes"],
            )
            self._assert_complete_unknown_inventory(document["segments"][0])

    def test_upstream_indeterminate_blocks_otherwise_certified_result(self):
        source = admitted_source(
            self.rig, ticks=(0, 1), upstream_certified=False
        )
        with patched_pipeline(
            source, self.context, self.locators,
            driver=self._certified_driver,
        ):
            document = analyze_body_sway_dynamic_seam_source(source).document
        self.assertEqual("indeterminate", document["status"])
        self.assertTrue(document["summary"]["all_seam_segments_certified"])
        self.assertIn(
            "upstream_continuous_preview_model_structural_unproven",
            document["summary"]["reason_codes"],
        )
        self.assertFalse(document["claims"][
            "continuous_preview_model_reviewed_anchor_proximity_within_"
            "engineering_tolerance"
        ])

    def test_compiler_is_frozen_copy_isolated_zero_write_and_narrow(self):
        source = admitted_source(self.rig, ticks=(0, 1))
        with patched_pipeline(
            source, self.context, self.locators,
            driver=self._certified_driver,
        ) as (_analysis, compiler_admission, _driver), patch(
            "builtins.open", side_effect=AssertionError("write attempted")
        ):
            first = compile_body_sway_dynamic_seam_probe(source)
            second = compile_body_sway_dynamic_seam_probe(source)
        self.assertEqual(2, compiler_admission.call_count)
        self.assertEqual(first.canonical_bytes, second.canonical_bytes)
        document = first.document
        self.assertEqual(FORMAT, document["format"])
        self.assertEqual(FORMAT_VERSION, document["format_version"])
        self.assertEqual(CERTIFIED_STATUS, document["status"])
        self.assertTrue(document["claims"][
            "continuous_preview_model_reviewed_anchor_proximity_within_"
            "engineering_tolerance"
        ])
        for claim in (
            "dynamic_seam_safety", "visual_seam_quality",
            "runtime_equivalence", "publishable_timeline",
            "release_authority",
        ):
            self.assertFalse(document["claims"][claim])
        self.assertEqual("blocked", document["release_gate"]["status"])
        source["source_set_sha256"] = "f" * 64
        document["source"]["source_set_sha256"] = "e" * 64
        self.assertEqual("a" * 64, first.document["source"][
            "source_set_sha256"
        ])

    def test_real_region_mesh_locator_driver_vertical_slice(self):
        source = admitted_source(self.rig, ticks=(0, 1))
        kinds = {
            locator.attachment_type
            for relationship in self.locators.relationships
            for pair in relationship.anchors
            for locator in (pair.parent, pair.child)
        }
        self.assertEqual({"region", "mesh"}, kinds)
        with patched_pipeline(source, self.context, self.locators):
            document = analyze_body_sway_dynamic_seam_source(source).document
        self.assertEqual(CERTIFIED_STATUS, document["status"])
        self.assertEqual(1, document["summary"]["evaluated_box_count"])
        self.assertLess(
            document["summary"]["max_squared_distance_upper_px2"], 4.0
        )

    def _assert_complete_unknown_inventory(self, row):
        self.assertEqual(6, row["relationship_count"])
        self.assertEqual(
            row["pair_count"],
            sum(len(relation["pairs"])
                for relation in row["relationships"]),
        )
        self.assertIsNone(row["max_squared_distance_upper_px2"])
        self.assertTrue(all(
            pair["max_squared_distance_upper_px2"] is None
            for relation in row["relationships"]
            for pair in relation["pairs"]
        ))


if __name__ == "__main__":
    unittest.main()
