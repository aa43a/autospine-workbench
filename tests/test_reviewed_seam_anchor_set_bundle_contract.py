"""Pure contract tests for reviewed seam-anchor set bundles."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for candidate in (ROOT, SRC):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from autospine_workbench.immutable_bundle_fs import framed_bundle_sha256
from autospine_workbench.reviewed_seam_anchor_set_bundle_contract import (
    BUNDLE_ADDRESS_DOMAIN,
    DOCUMENT_NAMES,
    ReviewedSeamAnchorSetBundleContractError,
    build_reviewed_seam_anchor_set_bundle_contract,
    reviewed_seam_anchor_set_bundle_address_sha256,
)
from autospine_workbench.reviewed_seam_anchor_set_compiler import (
    compile_reviewed_seam_anchor_set,
)
from autospine_workbench.seam_anchor_review_decision import (
    build_seam_anchor_review_decision,
)
from tests.reviewed_seam_anchor_set_bundle_helpers import exact_bundle_values
from tests.seam_anchor_review_helpers import seam_review_rows


class ReviewedSeamAnchorSetBundleContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.candidates, self.decision, self.rig, self.reviewed_set = (
            exact_bundle_values()
        )

    def build(self, **changes):
        values = {
            "candidates": self.candidates.document,
            "decision": self.decision.document,
            "rig": self.rig,
            "reviewed_set": self.reviewed_set.document,
            **changes,
        }
        return build_reviewed_seam_anchor_set_bundle_contract(**values)

    def test_fixed_inventory_and_domain_separated_determinism(self):
        first = self.build()
        second = self.build(
            candidates=dict(reversed(list(self.candidates.document.items()))),
            decision=dict(reversed(list(self.decision.document.items()))),
            rig=dict(reversed(list(self.rig.items()))),
            reviewed_set=dict(
                reversed(list(self.reviewed_set.document.items()))
            ),
        )
        self.assertEqual(DOCUMENT_NAMES, first.inventory)
        self.assertEqual(first, second)
        self.assertEqual(
            first.bundle_sha256,
            reviewed_seam_anchor_set_bundle_address_sha256(
                first.document_bytes
            ),
        )
        self.assertNotEqual(
            first.bundle_sha256,
            framed_bundle_sha256(
                "other-domain/v1", DOCUMENT_NAMES, first.document_bytes
            ),
        )
        self.assertEqual(
            BUNDLE_ADDRESS_DOMAIN,
            "autospine-reviewed-seam-anchor-set-bundle-address/v1",
        )

    def test_decision_change_changes_set_and_bundle_addresses(self):
        changed_decision = build_seam_anchor_review_decision(
            self.candidates.document,
            self.rig,
            review={"reviewer_id": "artist-02", "notes": "new evidence"},
            decisions=seam_review_rows(self.candidates.document, "accept"),
        )
        changed_set = compile_reviewed_seam_anchor_set(
            self.candidates.document, changed_decision.document, self.rig
        )
        baseline = self.build()
        changed = self.build(
            decision=changed_decision.document,
            reviewed_set=changed_set.document,
        )
        self.assertNotEqual(baseline.decision_sha256, changed.decision_sha256)
        self.assertNotEqual(baseline.set_sha256, changed.set_sha256)
        self.assertNotEqual(baseline.bundle_sha256, changed.bundle_sha256)

    def test_stale_or_hand_edited_set_is_rejected(self):
        stale = deepcopy(self.reviewed_set.document)
        stale["source"]["seam_anchor_review_decision_sha256"] = "f" * 64
        with self.assertRaises(ReviewedSeamAnchorSetBundleContractError):
            self.build(reviewed_set=stale)

        changed = deepcopy(self.reviewed_set.document)
        changed["relationships"][0]["anchors"][0]["parent"][
            "local_xy_q4096"
        ][0] += 1
        with self.assertRaises(ReviewedSeamAnchorSetBundleContractError):
            self.build(reviewed_set=changed)

    def test_document_access_is_isolated_and_unknown_name_fails(self):
        contract = self.build()
        candidate = contract.document(DOCUMENT_NAMES[0])
        candidate.clear()
        self.assertEqual(
            self.candidates.document, contract.document(DOCUMENT_NAMES[0])
        )
        with self.assertRaises(KeyError):
            contract.document("latest.json")


if __name__ == "__main__":
    unittest.main()
