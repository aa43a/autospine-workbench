"""SeamAnchorCandidates v1 standalone validator and schema tests."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from autospine_workbench.seam_anchor_candidate_profile import (
    CLAIMS,
    GENERATOR,
    RELEASE_GATE,
    SEMANTICS,
    option_evidence_sha256,
    relationship_evidence_sha256,
)
from autospine_workbench.seam_anchor_candidate_validation import (
    RELATIONSHIP_PROFILE,
    SeamAnchorCandidateValidationError,
    require_seam_anchor_candidates,
    seam_anchor_candidates_sha256,
)
from autospine_workbench.seam_anchor_profile import (
    SEAM_SOURCE_IDENTITY_FIELDS,
)
from autospine_workbench.seam_anchor_sampling import SAMPLING_PROFILE

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover - optional dependency
    Draft202012Validator = None


ROOT = Path(__file__).resolve().parents[1]
SHA = "a" * 64


def _region(attachment_id, x):
    return {
        "attachment_id": attachment_id,
        "attachment_type": "region",
        "locator_type": "region-local-q4096",
        "local_xy_q4096": [x * 4096, 2 * 4096],
    }


def _mesh(attachment_id, x):
    return {
        "attachment_id": attachment_id,
        "attachment_type": "mesh",
        "locator_type": "mesh-barycentric-q65535",
        "triangle_index": 0,
        "vertex_indices": [0, 1, 2],
        "weights_q65535": [65535 - x, x, 0],
    }


def _overlap(contact_id="overlap.000"):
    return {
        "contact_id": contact_id,
        "mode": "overlap",
        "area": 16,
        "bbox_xywh": [10, 20, 8, 2],
        "centroid_xy": [13.5, 20.5],
        "variance_xy": [5.25, 0.25],
        "representative_xy": [13.0, 20.0],
        "error_radius_px": 2.345208,
        "overlap_ratios": [0.1, 0.2],
        "gap_distance_px": 0.0,
        "endpoints_xy": [[13.0, 20.0], [13.0, 20.0]],
    }


def _gap():
    return {
        "contact_id": "gap.000",
        "mode": "gap",
        "area": 0,
        "bbox_xywh": [1, 1, 4, 5],
        "centroid_xy": [2.5, 3.0],
        "variance_xy": [2.25, 4.0],
        "representative_xy": [2.5, 3.0],
        "error_radius_px": 2.5,
        "overlap_ratios": [0.0, 0.0],
        "gap_distance_px": 5.0,
        "endpoints_xy": [[1.0, 1.0], [4.0, 5.0]],
    }


def _candidate(relationship_id, parent, child, child_type="region"):
    child_locator = _region(child, 1) if child_type == "region" else _mesh(child, 1)
    child_locator_2 = _region(child, 2) if child_type == "region" else _mesh(child, 2)
    row = {
        "option_id": f"{relationship_id}.option.000",
        "parent_attachment_id": parent,
        "child_attachment_id": child,
        "parent_attachment_type": "region",
        "child_attachment_type": child_type,
        "status": "candidate",
        "reason_codes": [],
        "contact_evidence": _overlap(),
        "principal_axis": "x",
        "sampling_profile": SAMPLING_PROFILE,
        "anchors": [
            {
                "pair_id": "anchor.000", "parent": _region(parent, 1),
                "child": child_locator,
            },
            {
                "pair_id": "anchor.001", "parent": _region(parent, 2),
                "child": child_locator_2,
            },
        ],
    }
    return _seal_option(row)


def _unavailable(
    relationship_id, parent, child, reason, *, contact=None, sampled=False
):
    row = {
        "option_id": f"{relationship_id}.option.000",
        "parent_attachment_id": parent,
        "child_attachment_id": child,
        "parent_attachment_type": "region",
        "child_attachment_type": "region",
        "status": "unavailable",
        "reason_codes": [reason],
        "contact_evidence": contact,
        "principal_axis": "x" if sampled else None,
        "sampling_profile": SAMPLING_PROFILE if sampled else None,
        "anchors": [],
    }
    return _seal_option(row)


def _seal_option(row):
    row["evidence_sha256"] = option_evidence_sha256(row)
    return row


def _relationship(profile, options, reasons):
    identifier, relation, joint, side = profile
    row = {
        "relationship_id": identifier,
        "relation": relation,
        "joint": joint,
        "side": side,
        "status": "review_required" if any(
            option["status"] == "candidate" for option in options
        ) else "unobservable",
        "reason_codes": reasons,
        "options": options,
    }
    row["evidence_sha256"] = relationship_evidence_sha256(row)
    return row


def valid_candidates():
    profiles = RELATIONSHIP_PROFILE
    relationships = [
        _relationship(profiles[0], [
            _candidate(profiles[0][0], "torso", "arm.left")
        ], []),
        _relationship(profiles[1], [
            _candidate(profiles[1][0], "torso", "arm.right", "mesh")
        ], []),
        _relationship(profiles[2], [
            _unavailable(
                profiles[2][0], "pelvis", "leg.left",
                "GAP_LOCATOR_UNSUPPORTED_IN_V1", contact=_gap(),
            )
        ], ["GAP_LOCATOR_UNSUPPORTED_IN_V1"]),
        _relationship(profiles[3], [
            _unavailable(
                profiles[3][0], "pelvis", "leg.right", "CONTACT_MASK_EMPTY"
            )
        ], ["CONTACT_MASK_EMPTY"]),
        _relationship(profiles[4], [
            _unavailable(
                profiles[4][0], "leg.left", "foot.left",
                "SAMPLING_BUDGET_EXCEEDED", contact=_overlap(), sampled=True,
            )
        ], ["SAMPLING_BUDGET_EXCEEDED"]),
        _relationship(
            profiles[5], [], ["NO_SUPPORTED_CANDIDATE_PAIR"]
        ),
    ]
    return {
        "format": "autospine-seam-anchor-candidates",
        "format_version": 1,
        "project_id": "sample.project",
        "source": {field: SHA for field in SEAM_SOURCE_IDENTITY_FIELDS},
        "generator": deepcopy(GENERATOR),
        "semantics": deepcopy(SEMANTICS),
        "relationships": relationships,
        "claims": deepcopy(CLAIMS),
        "release_gate": deepcopy(RELEASE_GATE),
        "summary": {
            "status": "manual_review_required",
            "relationship_count": 6,
            "review_required_count": 2,
            "unobservable_count": 4,
            "option_count": 5,
            "candidate_option_count": 2,
            "unavailable_option_count": 3,
            "anchor_pair_count": 4,
        },
    }


class SeamAnchorCandidateValidationTests(unittest.TestCase):
    def assert_invalid(self, mutate):
        document = valid_candidates()
        mutate(document)
        with self.assertRaises(SeamAnchorCandidateValidationError):
            require_seam_anchor_candidates(document)

    def test_valid_document_and_canonical_hash(self):
        document = valid_candidates()
        require_seam_anchor_candidates(document)
        reordered = json.loads(json.dumps(document, sort_keys=True))
        self.assertEqual(
            seam_anchor_candidates_sha256(document),
            seam_anchor_candidates_sha256(reordered),
        )

    def test_top_source_and_fixed_boundary_are_closed(self):
        cases = (
            lambda row: row.__setitem__("extra", True),
            lambda row: row["source"].pop("rig_sha256"),
            lambda row: row["source"].__setitem__("rig_sha256", SHA.upper()),
            lambda row: row["generator"].__setitem__("alpha_threshold", 8.0),
            lambda row: row["semantics"].__setitem__(
                "motion_or_clip_input_admitted", True
            ),
            lambda row: row["claims"].__setitem__("release_authority", True),
            lambda row: row["release_gate"]["reasons"].pop(),
            lambda row: row["release_gate"].__setitem__(
                "reasons", tuple(row["release_gate"]["reasons"])
            ),
        )
        for mutate in cases:
            with self.subTest(mutate=mutate):
                self.assert_invalid(mutate)

    def test_relationship_rows_status_reasons_and_hash_are_derived(self):
        cases = (
            lambda row: row["relationships"].reverse(),
            lambda row: row["relationships"][0].__setitem__(
                "relationship_id", "seam.other.left"
            ),
            lambda row: row["relationships"][0].__setitem__(
                "status", "unobservable"
            ),
            lambda row: row["relationships"][5].__setitem__("reason_codes", []),
            lambda row: row["relationships"][2]["reason_codes"].extend(
                ["Z_REASON", "A_REASON"]
            ),
            lambda row: row["relationships"][0].__setitem__(
                "evidence_sha256", "b" * 64
            ),
        )
        for mutate in cases:
            with self.subTest(mutate=mutate):
                self.assert_invalid(mutate)

    def test_option_status_ids_reasons_types_and_hash_fail_closed(self):
        cases = (
            lambda row: row["relationships"][0]["options"][0].__setitem__(
                "option_id", "option.000"
            ),
            lambda row: row["relationships"][0]["options"][0].__setitem__(
                "status", "accepted"
            ),
            lambda row: row["relationships"][0]["options"][0]["reason_codes"]
            .append("SHOULD_BE_EMPTY"),
            lambda row: row["relationships"][2]["options"][0].__setitem__(
                "reason_codes", []
            ),
            lambda row: row["relationships"][0]["options"][0].__setitem__(
                "parent_attachment_id", "arm.left"
            ),
            lambda row: row["relationships"][0]["options"][0].__setitem__(
                "evidence_sha256", "b" * 64
            ),
            lambda row: row["relationships"][0]["options"][0].__setitem__(
                "extra", True
            ),
        )
        for mutate in cases:
            with self.subTest(mutate=mutate):
                self.assert_invalid(mutate)

    def test_contact_evidence_and_sampling_correlations_fail_closed(self):
        cases = (
            lambda row: row["relationships"][0]["options"][0]
            ["contact_evidence"].__setitem__("mode", "gap"),
            lambda row: row["relationships"][0]["options"][0]
            ["contact_evidence"].__setitem__("area", 0),
            lambda row: row["relationships"][0]["options"][0]
            ["contact_evidence"].__setitem__("gap_distance_px", float("nan")),
            lambda row: row["relationships"][0]["options"][0]
            ["contact_evidence"]["endpoints_xy"][1].__setitem__(0, 14.0),
            lambda row: row["relationships"][0]["options"][0].__setitem__(
                "principal_axis", "y"
            ),
            lambda row: row["relationships"][2]["options"][0].__setitem__(
                "principal_axis", "x"
            ),
            lambda row: row["relationships"][4]["options"][0].__setitem__(
                "sampling_profile", None
            ),
        )
        for mutate in cases:
            with self.subTest(mutate=mutate):
                self.assert_invalid(mutate)

    def test_locator_shapes_binding_weights_and_endpoint_uniqueness(self):
        cases = (
            lambda row: row["relationships"][0]["options"][0]["anchors"][0]
            ["parent"].__setitem__("attachment_id", "other"),
            lambda row: row["relationships"][0]["options"][0]["anchors"][0]
            ["parent"]["local_xy_q4096"].__setitem__(0, -1),
            lambda row: row["relationships"][1]["options"][0]["anchors"][0]
            ["child"]["weights_q65535"].__setitem__(0, 0),
            lambda row: row["relationships"][1]["options"][0]["anchors"][0]
            ["child"]["vertex_indices"].__setitem__(2, 1),
            lambda row: row["relationships"][0]["options"][0]["anchors"][1]
            .__setitem__("pair_id", "anchor.000"),
            lambda row: row["relationships"][0]["options"][0]["anchors"][1]
            .__setitem__("parent", deepcopy(
                row["relationships"][0]["options"][0]["anchors"][0]["parent"]
            )),
        )
        for mutate in cases:
            with self.subTest(mutate=mutate):
                self.assert_invalid(mutate)

    def test_mesh_mesh_never_becomes_candidate(self):
        def mutate(document):
            option = document["relationships"][1]["options"][0]
            option["parent_attachment_type"] = "mesh"
            for anchor in option["anchors"]:
                anchor["parent"] = _mesh("torso", 3)

        self.assert_invalid(mutate)

    def test_resealed_impossible_compiler_states_fail_closed(self):
        def omitted_option_reason(document):
            document["relationships"][3]["reason_codes"] = [
                "CHILD_SOURCE_LAYER_MISSING"
            ]

        def missing_overlap_sampling(document):
            option = document["relationships"][4]["options"][0]
            option["principal_axis"] = None
            option["sampling_profile"] = None

        def five_generated_anchors(document):
            option = document["relationships"][0]["options"][0]
            for value in (3, 4, 5):
                option["anchors"].append({
                    "pair_id": f"anchor.{value - 1:03d}",
                    "parent": _region("torso", value),
                    "child": _region("arm.left", value),
                })

        def unavailable_mesh_mesh(document):
            option = document["relationships"][3]["options"][0]
            option["parent_attachment_type"] = "mesh"
            option["child_attachment_type"] = "mesh"

        def extra_option_diagnostic(document):
            document["relationships"][0]["reason_codes"] = [
                "CONTACT_MASK_EMPTY"
            ]

        def pair_budget_with_options(document):
            document["relationships"][0]["reason_codes"] = [
                "RELATION_CANDIDATE_PAIR_BUDGET_EXCEEDED"
            ]

        for mutate in (
            omitted_option_reason, missing_overlap_sampling,
            five_generated_anchors, unavailable_mesh_mesh,
            extra_option_diagnostic, pair_budget_with_options,
        ):
            document = valid_candidates()
            mutate(document)
            _reseal(document)
            with self.subTest(mutate=mutate), self.assertRaises(
                SeamAnchorCandidateValidationError
            ):
                require_seam_anchor_candidates(document)

    def test_summary_byte_budget_and_non_json_inputs_fail_closed(self):
        cases = (
            lambda row: row["summary"].__setitem__("candidate_option_count", 3),
            lambda row: row["summary"].__setitem__("anchor_pair_count", 4.0),
            lambda row: row["summary"].__setitem__("extra", 0),
            lambda row: row.__setitem__("project_id", object()),
        )
        for mutate in cases:
            with self.subTest(mutate=mutate):
                self.assert_invalid(mutate)
        with patch(
            "autospine_workbench.seam_anchor_candidate_validation.MAX_DOCUMENT_BYTES",
            1,
        ):
            with self.assertRaises(SeamAnchorCandidateValidationError):
                require_seam_anchor_candidates(valid_candidates())
        with self.assertRaises(SeamAnchorCandidateValidationError):
            require_seam_anchor_candidates(None)

    def test_container_subclasses_are_rejected_before_custom_iteration(self):
        class LyingList(list):
            def __len__(self):
                return 0

            def __iter__(self):
                raise AssertionError("lying list was iterated")

        class LyingDict(dict):
            def __iter__(self):
                raise AssertionError("lying dict was iterated")

        document = valid_candidates()
        document["relationships"] = LyingList(document["relationships"])
        with self.assertRaises(SeamAnchorCandidateValidationError):
            require_seam_anchor_candidates(document)
        with self.assertRaises(SeamAnchorCandidateValidationError):
            require_seam_anchor_candidates(LyingDict(valid_candidates()))

    @unittest.skipIf(Draft202012Validator is None, "jsonschema is optional")
    def test_schema_parity_for_valid_and_structural_failures(self):
        schema = json.loads(
            (ROOT / "schemas" / "seam-anchor-candidates-v1.schema.json")
            .read_text(encoding="utf-8")
        )
        validator = Draft202012Validator(schema)
        validator.validate(valid_candidates())
        mutations = (
            lambda row: row.__setitem__("extra", True),
            lambda row: row["relationships"].reverse(),
            lambda row: row["relationships"][0]["options"][0].__setitem__(
                "status", "accepted"
            ),
            lambda row: row["relationships"][0]["options"][0]["anchors"][0]
            ["parent"].__setitem__("local_xy_q4096", [-1, 0]),
            lambda row: row["relationships"][0]["options"][0]
            ["contact_evidence"].__setitem__("extra", True),
            lambda row: row["relationships"][4]["options"][0].__setitem__(
                "sampling_profile", None
            ),
            lambda row: row["relationships"][3]["options"][0].__setitem__(
                "parent_attachment_type", "mesh"
            ) or row["relationships"][3]["options"][0].__setitem__(
                "child_attachment_type", "mesh"
            ),
            lambda row: row["relationships"][0]["options"][0]["anchors"].extend(
                deepcopy(row["relationships"][0]["options"][0]["anchors"][:1])
                * 3
            ),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                document = valid_candidates()
                mutate(document)
                self.assertFalse(validator.is_valid(document))


def _reseal(document):
    totals = {
        "review_required_count": 0, "unobservable_count": 0,
        "option_count": 0, "candidate_option_count": 0,
        "unavailable_option_count": 0, "anchor_pair_count": 0,
    }
    for relationship in document["relationships"]:
        for option in relationship["options"]:
            option.pop("evidence_sha256", None)
            _seal_option(option)
            totals["option_count"] += 1
            totals[f"{option['status']}_option_count"] += 1
            totals["anchor_pair_count"] += len(option["anchors"])
        relationship["status"] = "review_required" if any(
            option["status"] == "candidate"
            for option in relationship["options"]
        ) else "unobservable"
        totals[f"{relationship['status']}_count"] += 1
        relationship.pop("evidence_sha256", None)
        relationship["evidence_sha256"] = relationship_evidence_sha256(
            relationship
        )
    document["summary"] = {
        "status": "manual_review_required", "relationship_count": 6,
        **totals,
    }


if __name__ == "__main__":
    unittest.main()
