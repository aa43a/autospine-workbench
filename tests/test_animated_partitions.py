"""Bilateral preview integration retains every source pixel and decision."""

import base64
from copy import deepcopy
from types import SimpleNamespace
import unittest

from autospine_workbench.automation.animated_partitions import build_partitions, expand_inputs
from tests.test_structure_candidates import inputs


class AnimatedPartitionTests(unittest.TestCase):
    def test_ambiguous_components_do_not_force_partition(self):
        args = inputs()
        source = SimpleNamespace(**dict(zip(
            ("candidate", "assisted", "skeleton", "bindings", "draft", "images"), args)))
        before = deepcopy(source.draft)
        partitions = build_partitions(source)
        self.assertEqual(source.draft, before)
        # The fixture's feet are far from these two components: preserve original context.
        self.assertEqual(partitions, [])

    def test_expansion_has_independent_texture_names_without_losing_original_identity(self):
        raw = b"exact-png-bytes"
        source = SimpleNamespace(candidate={"layers": [{"layer_id": "a"}, {"layer_id": "b"}]},
                                 images={"a": raw, "b": raw}, skeleton={}, source_addresses={})
        part = {"source_layer_id": "a", "layers": [{"layer_id": "a-l", "source_layer_id": "a"},
                {"layer_id": "a-r", "source_layer_id": "a"}, {"layer_id": "a-residual", "source_layer_id": "a"}],
                "images_base64": {"a-l": base64.b64encode(raw).decode()}}
        expanded = expand_inputs(source, [part])
        self.assertEqual([r["layer_id"] for r in expanded.candidate["layers"]], ["a-l", "a-r", "a-residual", "b"])
        self.assertEqual(expanded.images["a-l"], raw)
        self.assertEqual(source.candidate["layers"], [{"layer_id": "a"}, {"layer_id": "b"}])


if __name__ == "__main__":
    unittest.main()
