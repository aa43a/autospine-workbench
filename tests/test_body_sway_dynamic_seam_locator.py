"""P10.5d exact static preparation tests for dynamic seam locators."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
from fractions import Fraction
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.body_sway_dynamic_seam_locator import (  # noqa: E402
    BodySwayDynamicSeamLocatorError,
    prepare_body_sway_dynamic_seam_locators,
    resolve_prepared_dynamic_seam_setup_exact,
)
from autospine_workbench.body_sway_dynamic_seam_moments import (  # noqa: E402
    fraction_to_outward_interval,
    outward_dynamic_seam_moments,
)
from autospine_workbench.body_sway_probe_geometry_context import (  # noqa: E402
    prepare_body_sway_geometry_context,
)
from autospine_workbench.resolved_project import canonical_sha256  # noqa: E402
from autospine_workbench.seam_anchor_locators import (  # noqa: E402
    resolve_attachment_locator_exact,
)
from tests.body_sway_dynamic_seam_locator_helpers import (  # noqa: E402
    four_vertex_fixture,
    reviewed_set,
    second_mesh,
    target_for,
)


class DynamicSeamLocatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rig, target = four_vertex_fixture()
        cls.context = prepare_body_sway_geometry_context(cls.rig, target)
        cls.reviewed = reviewed_set(cls.rig)

    def prepare(self, rig=None, context=None, reviewed=None):
        return prepare_body_sway_dynamic_seam_locators(
            rig or self.rig, context or self.context,
            reviewed or self.reviewed,
        )

    def test_supports_three_v1_type_pairs_and_retains_only_references(self):
        prepared = self.prepare()
        self.assertEqual(6, len(prepared.relationships))
        self.assertEqual(
            [("region", "region"), ("region", "mesh"),
             ("mesh", "region")] * 2,
            [(row.anchors[0].parent.attachment_type,
              row.anchors[0].child.attachment_type)
             for row in prepared.relationships],
        )
        attachments = {row["id"]: row for row in self.rig["attachments"]}
        for source_row, prepared_row in zip(
            self.reviewed["relationships"], prepared.relationships,
            strict=True,
        ):
            for source_pair, prepared_pair in zip(
                source_row["anchors"], prepared_row.anchors, strict=True,
            ):
                for side in ("parent", "child"):
                    source = source_pair[side]
                    endpoint = getattr(prepared_pair, side)
                    expected = resolve_attachment_locator_exact(
                        source, attachments[source["attachment_id"]]
                    )
                    self.assertEqual(expected, endpoint.setup_canvas_xy)
                    dynamic = resolve_prepared_dynamic_seam_setup_exact(
                        endpoint
                    )
                    if source["attachment_type"] == "region":
                        self.assertEqual(expected, dynamic)
                    else:
                        self.assertTrue(all(
                            abs(left - right) <= Fraction(1, 8192)
                            for left, right in zip(
                                expected, dynamic, strict=True
                            )
                        ))
                    self.assertEqual(
                        1 if source["attachment_type"] == "region" else 3,
                        len(endpoint.vertices),
                    )
        mesh = prepared.relationships[1].anchors[0].child
        self.assertEqual(4, len(attachments["leg-left"]["vertices"]))
        self.assertEqual(
            tuple(self.reviewed["relationships"][1]["anchors"][0]
                  ["child"]["vertex_indices"]),
            tuple(row.vertex_index for row in mesh.vertices),
        )

    def test_exact_moments_have_tight_outward_binary64_enclosures(self):
        mesh = self.prepare().relationships[1].anchors[0].child
        source = self.reviewed["relationships"][1]["anchors"][0]["child"]
        prepared_mesh = next(
            row for row in self.context.attachments
            if row.attachment_id == "leg-left"
        )
        expected = {}
        for term, index, q_weight in zip(
            mesh.vertices, source["vertex_indices"],
            source["weights_q65535"], strict=True,
        ):
            bind = prepared_mesh.binding._vertices[index]
            self.assertEqual(
                tuple(Fraction.from_float(value) for value in bind),
                term.setup_canvas_xy,
            )
            self.assertEqual(Fraction(q_weight, 65_535), term.locator_weight)
            for influence, (bone_index, weight) in zip(
                term.influences, prepared_mesh.binding._influences[index],
                strict=True,
            ):
                self.assertEqual(Fraction.from_float(weight), influence.weight)
                coefficient = Fraction(q_weight, 65_535) \
                    * Fraction.from_float(weight)
                row = expected.setdefault(
                    (bone_index, influence.bone_id),
                    [Fraction(0), Fraction(0), Fraction(0)],
                )
                row[0] += coefficient
                row[1] += coefficient * Fraction.from_float(bind[0])
                row[2] += coefficient * Fraction.from_float(bind[1])
        self.assertEqual(
            expected,
            {(row.bone_index, row.bone_id): [
                row.affine_weight, row.setup_x_moment,
                row.setup_y_moment,
            ] for row in mesh.moments},
        )
        dynamic_setup = resolve_prepared_dynamic_seam_setup_exact(mesh)
        self.assertNotEqual(mesh.setup_canvas_xy, dynamic_setup)
        for exact, outward in zip(
            mesh.moments, outward_dynamic_seam_moments(mesh.moments),
            strict=True,
        ):
            for value, interval in (
                (exact.affine_weight, outward.affine_weight),
                (exact.setup_x_moment, outward.setup_x_moment),
                (exact.setup_y_moment, outward.setup_y_moment),
            ):
                self.assertLessEqual(Fraction.from_float(interval.lower), value)
                self.assertGreaterEqual(Fraction.from_float(interval.upper), value)
        exact = Fraction(1, 65_535)
        interval = fraction_to_outward_interval(exact)
        self.assertLess(interval.lower, interval.upper)
        self.assertLessEqual(Fraction.from_float(interval.lower), exact)
        self.assertGreaterEqual(Fraction.from_float(interval.upper), exact)
        half = fraction_to_outward_interval(Fraction(1, 2))
        self.assertEqual((0.5, 0.5), (half.lower, half.upper))
        with self.assertRaises(ValueError):
            fraction_to_outward_interval(1)  # type: ignore[arg-type]

    def test_mesh_static_to_binary_bind_delta_exceeding_half_step_fails(self):
        exact_resolver = resolve_attachment_locator_exact

        def shifted(locator, attachment):
            point = exact_resolver(locator, attachment)
            if locator["attachment_type"] == "mesh":
                return point[0] + Fraction(1, 4096), point[1]
            return point

        with patch(
            "autospine_workbench.body_sway_dynamic_seam_locator."
            "resolve_attachment_locator_exact",
            side_effect=shifted,
        ), self.assertRaisesRegex(
            BodySwayDynamicSeamLocatorError, "Q4096 setup tolerance",
        ):
            self.prepare()

    def test_preparation_is_deterministic_frozen_and_copy_isolated(self):
        first, second = self.prepare(), self.prepare()
        self.assertEqual(first, second)
        self.assertIs(self.context.skinning_rig, first._rig)
        self.assertNotIn("_rig=", repr(first))
        changed_rig = deepcopy(self.rig)
        changed_rig["bones"][0]["setup"]["x"] += 1
        duplicate_context = prepare_body_sway_geometry_context(
            changed_rig, target_for(changed_rig)
        )
        changed_reviewed = deepcopy(self.reviewed)
        changed_reviewed["source"]["p3_rig_sha256"] = canonical_sha256(
            changed_rig
        )
        duplicate = self.prepare(
            rig=changed_rig, context=duplicate_context,
            reviewed=changed_reviewed,
        )
        self.assertEqual(first._rig.bone_ids, duplicate._rig.bone_ids)
        self.assertIsNot(first._rig, duplicate._rig)
        before = repr(first)
        rig, reviewed = deepcopy(self.rig), deepcopy(self.reviewed)
        isolated = self.prepare(rig=rig, reviewed=reviewed)
        rig["attachments"][0]["vertices"][0][0] += 1000
        reviewed["relationships"][0]["anchors"].clear()
        self.assertEqual(before, repr(first))
        self.assertEqual(first, isolated)
        with self.assertRaises(FrozenInstanceError):
            first.project_id = "changed"  # type: ignore[misc]

    def test_wrong_address_and_forged_context_fail_closed(self):
        wrong = deepcopy(self.reviewed)
        wrong["source"]["p3_rig_sha256"] = "0" * 64
        with self.assertRaisesRegex(
            BodySwayDynamicSeamLocatorError, "different P3 RigIR",
        ):
            self.prepare(reviewed=wrong)
        forged = replace(
            self.context, attachments=tuple(reversed(self.context.attachments))
        )
        with self.assertRaisesRegex(
            BodySwayDynamicSeamLocatorError, "inventory differs",
        ):
            self.prepare(context=forged)

    def test_slot_topology_weight_and_type_tampering_fail_closed(self):
        cases = []
        slotted = deepcopy(self.rig)
        slotted["attachments"][0]["slot"] = "torso"
        cases.append((slotted, deepcopy(self.reviewed), "slot"))
        weighted = deepcopy(self.rig)
        weighted["attachments"][0]["weights"][0] = [
            {"bone": "thigh.left", "weight": 0.5000001},
            {"bone": "calf.left", "weight": 0.4999999},
        ]
        cases.append((weighted, deepcopy(self.reviewed), "weights differ"))
        topology = deepcopy(self.reviewed)
        locator = topology["relationships"][1]["anchors"][0]["child"]
        locator["vertex_indices"] = list(reversed(locator["vertex_indices"]))
        cases.append((deepcopy(self.rig), topology, "topology"))
        typed = deepcopy(self.reviewed)
        typed["relationships"][0]["anchors"][0]["parent"][
            "attachment_type"
        ] = "mesh"
        cases.append((deepcopy(self.rig), typed, "locator"))
        for rig, reviewed, reason in cases:
            with self.subTest(reason=reason):
                reviewed["source"]["p3_rig_sha256"] = canonical_sha256(rig)
                with self.assertRaises(BodySwayDynamicSeamLocatorError):
                    self.prepare(rig=rig, reviewed=reviewed)

    def test_mesh_mesh_is_explicitly_unsupported_in_v1(self):
        rig, context = second_mesh(self.rig, self.context)
        reviewed = reviewed_set(rig)
        with self.assertRaisesRegex(
            BodySwayDynamicSeamLocatorError, "Mesh-mesh.*unsupported in v1",
        ):
            self.prepare(rig=rig, context=context, reviewed=reviewed)

    def test_production_modules_remain_bounded(self):
        for name in (
            "body_sway_dynamic_seam_locator.py",
            "body_sway_dynamic_seam_locator_fields.py",
            "body_sway_dynamic_seam_moments.py",
        ):
            lines = (SRC / "autospine_workbench" / name).read_text(
                encoding="utf-8"
            ).splitlines()
            self.assertLessEqual(len(lines), 300, name)

if __name__ == "__main__":
    unittest.main()
