"""Exact-address tests for P10.5b seam-anchor review."""

from __future__ import annotations

import unittest

from autospine_workbench.seam_anchor_review_address import (
    ExactSeamAnchorReviewAddress,
    ExactSeamAnchorReviewAddressError,
)


class ExactSeamAnchorReviewAddressTests(unittest.TestCase):
    def test_exact_reader_arguments_and_public_document(self):
        address = ExactSeamAnchorReviewAddress(
            "sample", "a" * 64, "b" * 64, "c" * 64
        )
        self.assertEqual(("sample", "a" * 64),
                         address.manifest_reader_arguments)
        self.assertEqual(("sample", "b" * 64, "c" * 64),
                         address.mesh_reader_arguments)
        self.assertEqual({
            "project_id": "sample",
            "layer_manifest_sha256": "a" * 64,
            "p3_rig_sha256": "b" * 64,
            "p3_bundle_sha256": "c" * 64,
        }, address.public_document())

    def test_discovery_aliases_and_malformed_values_fail_closed(self):
        cases = (
            ("../sample", "a" * 64, "b" * 64, "c" * 64),
            ("sample", "latest", "b" * 64, "c" * 64),
            ("sample", "a" * 64, "B" * 64, "c" * 64),
            ("sample", "a" * 64, "b" * 64, ""),
        )
        for values in cases:
            with self.subTest(values=values), self.assertRaises(
                ExactSeamAnchorReviewAddressError
            ):
                ExactSeamAnchorReviewAddress(*values)


if __name__ == "__main__":
    unittest.main()
