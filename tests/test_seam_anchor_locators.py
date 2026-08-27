"""Contract tests for attachment-local seam anchor locators."""

from __future__ import annotations

from copy import deepcopy
import unittest

from autospine_workbench.seam_anchor_locators import (
    MESH_QUANTIZATION,
    SeamAnchorLocatorError,
    make_attachment_locator,
    resolve_attachment_locator,
)
from autospine_workbench.seam_anchor_sampling import (
    SeamAnchorUnsupportedError,
    validate_anchor_pairs,
)


def region(identifier="region-a"):
    return {
        "id": identifier, "type": "region",
        "canvas_offset_xy": [0, 0], "size": [10, 10],
    }


def mesh(identifier="mesh-b"):
    return {
        "id": identifier, "type": "mesh",
        "canvas_offset_xy": [0, 0],
        "vertices": [[0, 0], [10, 0], [0, 10], [10, 10]],
        "triangles": [0, 1, 2, 1, 3, 2],
    }


def pair(pair_id, attachment_a, point_a, attachment_b, point_b):
    return {
        "pair_id": pair_id,
        "a": make_attachment_locator(attachment_a, point_a),
        "b": make_attachment_locator(attachment_b, point_b),
    }


class AttachmentLocatorTests(unittest.TestCase):
    def test_region_half_step_rounds_up_and_boundaries_resolve(self) -> None:
        attachment = region()
        half_step = make_attachment_locator(
            attachment, [1 / 8192, 1 / 8192]
        )
        self.assertEqual([1, 1], half_step["local_xy_q4096"])
        self.assertEqual(
            (1 / 4096, 1 / 4096),
            resolve_attachment_locator(half_step, attachment),
        )
        maximum = make_attachment_locator(attachment, [10, 10])
        self.assertEqual([40960, 40960], maximum["local_xy_q4096"])
        self.assertEqual((10.0, 10.0), resolve_attachment_locator(
            maximum, attachment
        ))

    def test_region_outside_and_tampered_identity_are_rejected(self) -> None:
        attachment = region()
        with self.assertRaisesRegex(SeamAnchorLocatorError, "outside"):
            make_attachment_locator(attachment, [-0.01, 5])
        locator = make_attachment_locator(attachment, [2, 3])
        locator["local_xy_q4096"][0] = 40961
        with self.assertRaisesRegex(SeamAnchorLocatorError, "bounds"):
            resolve_attachment_locator(locator, attachment)
        locator = make_attachment_locator(attachment, [2, 3])
        locator["attachment_id"] = "other"
        with self.assertRaisesRegex(SeamAnchorLocatorError, "identity"):
            resolve_attachment_locator(locator, attachment)

    def test_mesh_uses_first_containing_triangle_and_never_nearest_vertex(self) -> None:
        attachment = mesh()
        locator = make_attachment_locator(attachment, [5, 5])
        self.assertEqual(0, locator["triangle_index"])
        self.assertEqual([0, 1, 2], locator["vertex_indices"])
        resolved = resolve_attachment_locator(locator, attachment)
        self.assertAlmostEqual(5.0, resolved[0], places=3)
        self.assertAlmostEqual(5.0, resolved[1], places=3)
        with self.assertRaisesRegex(SeamAnchorLocatorError, "outside every"):
            make_attachment_locator(attachment, [12, 12])

    def test_barycentric_half_step_is_deterministic_and_sum_is_exact(self) -> None:
        attachment = {
            "id": "unit", "type": "mesh", "canvas_offset_xy": [5, 7],
            "vertices": [[0, 0], [1, 0], [0, 1]],
            "triangles": [0, 1, 2],
        }
        locator = make_attachment_locator(attachment, [5.5, 7])
        self.assertEqual([32768, 32767, 0], locator["weights_q65535"])
        self.assertEqual(MESH_QUANTIZATION, sum(locator["weights_q65535"]))
        self.assertEqual(locator, make_attachment_locator(
            attachment, [5.5, 7]
        ))

    def test_mesh_triangle_and_topology_tampering_are_rejected(self) -> None:
        attachment = mesh()
        locator = make_attachment_locator(attachment, [2, 2])
        forged = deepcopy(locator)
        forged["vertex_indices"] = [0, 2, 1]
        with self.assertRaisesRegex(SeamAnchorLocatorError, "topology changed"):
            resolve_attachment_locator(forged, attachment)
        shared_edge = {
            "attachment_id": "mesh-b", "attachment_type": "mesh",
            "locator_type": "mesh-barycentric-q65535",
            "triangle_index": 0, "vertex_indices": [0, 1, 2],
            "weights_q65535": [0, 21845, 43690],
        }
        resolve_attachment_locator(shared_edge, attachment)
        forged = deepcopy(shared_edge)
        forged["triangle_index"] = 1
        forged["vertex_indices"] = [1, 3, 2]
        forged["weights_q65535"] = [21845, 0, 43690]
        with self.assertRaisesRegex(SeamAnchorLocatorError, "first containing"):
            resolve_attachment_locator(forged, attachment)
        broken = deepcopy(attachment)
        broken["triangles"] = [0, 0, 2]
        with self.assertRaisesRegex(SeamAnchorLocatorError, "topology"):
            resolve_attachment_locator(locator, broken)

    def test_near_shared_edge_recanonicalizes_after_weight_quantization(self):
        attachment = mesh()
        locator = make_attachment_locator(attachment, [5, 5.00001])
        self.assertEqual(0, locator["triangle_index"])
        self.assertEqual(locator, make_attachment_locator(
            attachment, resolve_attachment_locator(locator, attachment)
        ))

    def test_tiny_outside_points_are_rejected_without_hidden_clamping(self):
        with self.assertRaisesRegex(SeamAnchorLocatorError, "outside"):
            make_attachment_locator(region(), [-0.0000000005, 5])
        unit = {
            "id": "unit", "type": "mesh", "canvas_offset_xy": [0, 0],
            "vertices": [[0, 0], [1, 0], [0, 1]],
            "triangles": [0, 1, 2],
        }
        with self.assertRaisesRegex(SeamAnchorLocatorError, "outside"):
            make_attachment_locator(unit, [0.5, 0.5000000005])


class AnchorPairGeometryTests(unittest.TestCase):
    def test_region_region_and_region_mesh_are_supported(self) -> None:
        a, b, m = region("a"), region("b"), mesh("m")
        region_pairs = [
            pair("anchor.000", a, [1, 1], b, [1, 1]),
            pair("anchor.001", a, [3, 1], b, [3, 1]),
        ]
        resolved = validate_anchor_pairs(
            region_pairs, a, b, principal_axis="x"
        )
        self.assertEqual((1.0, 1.0), resolved[0].point_a_xy)
        mixed = [
            pair("anchor.000", a, [1, 1], m, [1, 1]),
            pair("anchor.001", a, [2, 1], m, [2, 1]),
        ]
        self.assertEqual(2, len(validate_anchor_pairs(
            mixed, a, m, principal_axis="x"
        )))

    def test_one_nine_duplicate_and_reverse_are_rejected(self) -> None:
        a, b = region("a"), region("b")
        one = [pair("anchor.000", a, [1, 1], b, [1, 1])]
        with self.assertRaisesRegex(SeamAnchorLocatorError, "count"):
            validate_anchor_pairs(one, a, b, principal_axis="x")
        nine = [pair(f"anchor.{index:03d}", a, [index, 1], b,
                     [index, 1]) for index in range(9)]
        with self.assertRaisesRegex(SeamAnchorLocatorError, "count"):
            validate_anchor_pairs(nine, a, b, principal_axis="x")
        duplicate = [one[0], {
            **deepcopy(one[0]), "pair_id": "anchor.001",
        }]
        with self.assertRaisesRegex(SeamAnchorLocatorError, "unique"):
            validate_anchor_pairs(duplicate, a, b, principal_axis="x")
        ordered = [
            pair("anchor.000", a, [1, 1], b, [1, 1]),
            pair("anchor.001", a, [3, 1], b, [3, 1]),
        ]
        with self.assertRaisesRegex(SeamAnchorLocatorError, "ordered"):
            validate_anchor_pairs(
                list(reversed(ordered)), a, b, principal_axis="x"
            )
        endpoint_reversed = [
            pair("anchor.000", a, [0, 0], b, [4, 0]),
            pair("anchor.001", a, [2, 1], b, [3, 1]),
        ]
        with self.assertRaisesRegex(SeamAnchorLocatorError, "ordered"):
            validate_anchor_pairs(
                endpoint_reversed, a, b, principal_axis="x"
            )

    def test_properly_crossing_connectors_are_rejected(self) -> None:
        a, b = region("a"), region("b")
        crossing = [
            pair("anchor.000", a, [0, 0], b, [4, 4]),
            pair("anchor.001", a, [1, 4], b, [5, 0]),
        ]
        with self.assertRaisesRegex(SeamAnchorLocatorError, "intersect"):
            validate_anchor_pairs(crossing, a, b, principal_axis="x")

    def test_collinear_overlap_is_rejected_as_an_intersection(self) -> None:
        a, b = region("a"), region("b")
        overlapping = [
            pair("anchor.000", a, [0, 0], b, [3, 0]),
            pair("anchor.001", a, [1, 0], b, [4, 0]),
        ]
        with self.assertRaisesRegex(SeamAnchorLocatorError, "intersect"):
            validate_anchor_pairs(overlapping, a, b, principal_axis="x")

    def test_pair_ids_are_canonical_not_merely_unique(self) -> None:
        a, b = region("a"), region("b")
        changed = [
            pair("pair.first", a, [1, 1], b, [1, 1]),
            pair("pair.second", a, [2, 1], b, [2, 1]),
        ]
        with self.assertRaisesRegex(SeamAnchorLocatorError, "canonical"):
            validate_anchor_pairs(changed, a, b, principal_axis="x")

    def test_mesh_mesh_has_explicit_version_one_reason(self) -> None:
        with self.assertRaises(SeamAnchorUnsupportedError) as captured:
            validate_anchor_pairs([], mesh("a"), mesh("b"), principal_axis="x")
        self.assertEqual("unsupported_in_v1", captured.exception.reason_code)


if __name__ == "__main__":
    unittest.main()
