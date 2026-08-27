"""Resource and support tests for relationship pair materialization."""

from __future__ import annotations

from types import SimpleNamespace
import unittest

from autospine_workbench.seam_anchor_relation_pairs import (
    materialize_supported_attachment_pairs,
)


def item(identifier, kind):
    return SimpleNamespace(
        identifier=identifier, kind=kind, sources=(identifier,)
    )


class SeamAnchorRelationPairTests(unittest.TestCase):
    def test_mesh_mesh_raw_cross_product_does_not_consume_supported_budget(self):
        parents = [item(f"pm.{index}", "mesh") for index in range(20)]
        children = [item(f"cm.{index}", "mesh") for index in range(20)]
        parents.append(item("parent.region", "region"))
        children.append(item("child.region", "region"))
        pairs, reasons = materialize_supported_attachment_pairs(
            parents, children, 41
        )
        self.assertEqual(41, len(pairs))
        self.assertIn("MESH_MESH_UNSUPPORTED", reasons)
        self.assertFalse(any(
            row["parent_attachment_type"] == "mesh"
            and row["child_attachment_type"] == "mesh"
            for row in pairs
        ))

    def test_supported_count_is_rejected_before_pair_dict_allocation(self):
        parents = [item("parent.region", "region")]
        children = [item("child.a", "region"), item("child.b", "mesh")]
        pairs, reasons = materialize_supported_attachment_pairs(
            parents, children, 1
        )
        self.assertEqual([], pairs)
        self.assertIn("RELATION_CANDIDATE_PAIR_BUDGET_EXCEEDED", reasons)


if __name__ == "__main__":
    unittest.main()
