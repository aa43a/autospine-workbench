"""Detached and exact-input attack tests for ReviewedSeamAnchorSet v1."""

from __future__ import annotations

from copy import deepcopy
import unittest

from autospine_workbench.reviewed_seam_anchor_set_binding_validation import (
    ReviewedSeamAnchorSetBindingValidationError,
    require_bound_reviewed_seam_anchor_set,
)
from autospine_workbench.reviewed_seam_anchor_set_compiler import (
    compile_reviewed_seam_anchor_set,
)
from autospine_workbench.reviewed_seam_anchor_set_validation import (
    ReviewedSeamAnchorSetValidationError,
    require_reviewed_seam_anchor_set,
)
from tests.reviewed_seam_anchor_set_helpers import reviewed_set_inputs


class ReviewedSeamAnchorSetValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.candidate, cls.decision, cls.rig = reviewed_set_inputs()
        cls.valid = compile_reviewed_seam_anchor_set(
            cls.candidate, cls.decision, cls.rig
        ).document

    def assert_detached_invalid(self, mutate):
        document = deepcopy(self.valid)
        mutate(document)
        with self.assertRaises(ReviewedSeamAnchorSetValidationError):
            require_reviewed_seam_anchor_set(document)

    def test_standalone_contract_rejects_extra_fields_order_and_overclaims(self):
        cases = (
            lambda row: row.__setitem__("extra", True),
            lambda row: row["relationships"][0].__setitem__(
                "option_id", "reselected"
            ),
            lambda row: row["relationships"].reverse(),
            lambda row: row["claims"].__setitem__(
                "dynamic_seam_safety", True
            ),
            lambda row: row["release_gate"].__setitem__("status", "ready"),
            lambda row: row["semantics"].__setitem__(
                "fallback_locator_allowed", True
            ),
            lambda row: row["compiler"].__setitem__(
                "candidate_reselection", "allowed"
            ),
            lambda row: row["summary"].__setitem__(
                "anchor_pair_count", 0
            ),
        )
        for mutate in cases:
            with self.subTest(mutate=mutate):
                self.assert_detached_invalid(mutate)

    def test_locator_fallback_crosswire_and_duplicate_fail_closed(self):
        def fallback(row):
            row["relationships"][0]["anchors"][0]["parent"][
                "locator_type"
            ] = "nearest-vertex-fallback"

        def crosswire(row):
            source = row["relationships"][2]["anchors"][0]["parent"]
            row["relationships"][0]["anchors"][1]["parent"] = deepcopy(source)

        def duplicate(row):
            source = row["relationships"][0]["anchors"][0]["parent"]
            row["relationships"][0]["anchors"][1]["parent"] = deepcopy(source)

        for mutate in (fallback, crosswire, duplicate):
            with self.subTest(mutate=mutate):
                self.assert_detached_invalid(mutate)

    def test_bound_validator_rejects_resealed_source_and_anchor_reselection(self):
        source_attack = deepcopy(self.valid)
        source_attack["source"]["seam_anchor_candidate_sha256"] = "a" * 64
        require_reviewed_seam_anchor_set(source_attack)
        with self.assertRaises(ReviewedSeamAnchorSetBindingValidationError):
            require_bound_reviewed_seam_anchor_set(
                source_attack, self.candidate, self.decision, self.rig
            )

        locator_attack = deepcopy(self.valid)
        locator = locator_attack["relationships"][0]["anchors"][0]["parent"]
        locator["local_xy_q4096"][0] += 1
        require_reviewed_seam_anchor_set(locator_attack)
        with self.assertRaises(ReviewedSeamAnchorSetBindingValidationError):
            require_bound_reviewed_seam_anchor_set(
                locator_attack, self.candidate, self.decision, self.rig
            )

    def test_exact_json_container_subclasses_are_rejected(self):
        class LyingDict(dict):
            pass

        class LyingList(list):
            pass

        with self.assertRaises(ReviewedSeamAnchorSetValidationError):
            require_reviewed_seam_anchor_set(LyingDict(self.valid))
        document = deepcopy(self.valid)
        document["relationships"] = LyingList(document["relationships"])
        with self.assertRaises(ReviewedSeamAnchorSetValidationError):
            require_reviewed_seam_anchor_set(document)

    def test_nested_rows_and_endpoints_reject_json_scalars_cleanly(self):
        attacks = (
            lambda document, value: document["relationships"].__setitem__(
                0, value
            ),
            lambda document, value: document["relationships"][0][
                "anchors"
            ].__setitem__(0, value),
            lambda document, value: document["relationships"][0][
                "anchors"
            ][0].__setitem__("parent", value),
        )
        for value in (None, False, 7, "not-an-object"):
            for attack in attacks:
                with self.subTest(value=value, attack=attack):
                    self.assert_detached_invalid(
                        lambda document, value=value, attack=attack:
                            attack(document, value)
                    )

    def test_project_candidate_decision_and_p3_cross_identity_fail(self):
        attacks = []
        project = deepcopy(self.valid)
        project["project_id"] = "other-project"
        attacks.append((project, self.candidate, self.decision, self.rig))
        rig = deepcopy(self.rig)
        rig["attachments"][0]["id"] = "other"
        attacks.append((self.valid, self.candidate, self.decision, rig))
        for document, candidate, decision, exact_rig in attacks:
            with self.subTest(document=document), self.assertRaises(
                ReviewedSeamAnchorSetBindingValidationError
            ):
                require_bound_reviewed_seam_anchor_set(
                    document, candidate, decision, exact_rig
                )


if __name__ == "__main__":
    unittest.main()
