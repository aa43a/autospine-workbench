"""Exact replay, binding, and budget tests for the P10.5d source."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for item in (ROOT, SRC):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from autospine_workbench.body_sway_continuous_proof_validation import (  # noqa: E402
    BodySwayContinuousProofValidationError,
)
from autospine_workbench.body_sway_dynamic_seam_profile import (  # noqa: E402
    SOURCE_FIELDS,
    SOURCE_HASH_DOMAIN,
    body_sway_dynamic_seam_source_sha256,
)
from autospine_workbench.body_sway_dynamic_seam_source import (  # noqa: E402
    BodySwayDynamicSeamSourceError,
    build_body_sway_dynamic_seam_source,
    require_body_sway_dynamic_seam_source,
)
from autospine_workbench.resolved_project import canonical_sha256  # noqa: E402
from autospine_workbench.reviewed_seam_anchor_set_bundle_contract import (  # noqa: E402
    build_reviewed_seam_anchor_set_bundle_contract,
)
from tests.body_sway_dynamic_seam_source_helpers import (  # noqa: E402
    build_kwargs,
)


PROOF_VALIDATOR = (
    "autospine_workbench.body_sway_dynamic_seam_source."
    "body_sway_continuous_proof_sha256"
)


def fake_proof_sha(document):
    return canonical_sha256(document)


class BodySwayDynamicSeamSourceTests(unittest.TestCase):
    def _build(self, *, mesh=False):
        values = build_kwargs(mesh=mesh)
        with patch(PROOF_VALIDATOR, side_effect=fake_proof_sha) as validator:
            source = build_body_sway_dynamic_seam_source(**values)
        self.assertEqual(1, validator.call_count)
        return values, source

    def test_region_and_mesh_sources_rebuild_exact_three_file_contract(self):
        for mesh in (False, True):
            with self.subTest(mesh=mesh):
                values, source = self._build(mesh=mesh)
                rig = values["continuous_proof"]["source"]["rig_ir"]
                contract = build_reviewed_seam_anchor_set_bundle_contract(
                    values["seam_anchor_candidates"],
                    values["seam_anchor_review_decision"], rig,
                    values["reviewed_seam_anchor_set"],
                )
                self.assertEqual(SOURCE_FIELDS, set(source))
                self.assertEqual(contract.bundle_sha256, source[
                    "reviewed_seam_anchor_set_bundle_sha256"
                ])
                self.assertEqual(contract.set_sha256, source[
                    "reviewed_seam_anchor_set_sha256"
                ])
                locator_types = {
                    endpoint["attachment_type"]
                    for row in source["reviewed_seam_anchor_set"][
                        "relationships"
                    ]
                    for pair in row["anchors"]
                    for endpoint in (pair["parent"], pair["child"])
                }
                self.assertIn("mesh" if mesh else "region", locator_types)
                with patch(PROOF_VALIDATOR, side_effect=fake_proof_sha):
                    replayed = require_body_sway_dynamic_seam_source(source)
                self.assertEqual(source, replayed)

    def test_proof_is_fully_recomputed_and_failure_is_closed(self):
        values = build_kwargs()
        failure = BodySwayContinuousProofValidationError("forged proof")
        with patch(PROOF_VALIDATOR, side_effect=failure) as validator:
            with self.assertRaisesRegex(
                BodySwayDynamicSeamSourceError, "forged proof"
            ):
                build_body_sway_dynamic_seam_source(**values)
        validator.assert_called_once_with(values["continuous_proof"])

    def test_explicit_framed_bundle_digest_is_mandatory(self):
        values = build_kwargs()
        values["reviewed_set_bundle_sha256"] = "0" * 64
        with patch(PROOF_VALIDATOR, side_effect=fake_proof_sha):
            with self.assertRaisesRegex(
                BodySwayDynamicSeamSourceError, "bundle digest"
            ):
                build_body_sway_dynamic_seam_source(**values)

    def test_manifest_p3_project_and_review_identity_attacks_fail(self):
        attacks = []
        project = build_kwargs()
        project["continuous_proof"]["project_id"] = "cross-project"
        attacks.append(project)
        manifest = build_kwargs()
        p3 = manifest["continuous_proof"]["source"] \
            ["amplitude_envelope_candidate"]["source"] \
            ["reviewed_probe_report"]["source"]["p3"]
        p3["layer_manifest_sha256"] = "a" * 64
        attacks.append(manifest)
        revision = build_kwargs()
        revision["reviewed_seam_anchor_set"]["source"][
            "review_revision"
        ] += 1
        attacks.append(revision)
        candidate = build_kwargs()
        candidate["seam_anchor_candidates"]["project_id"] = "cross-project"
        attacks.append(candidate)
        decision = build_kwargs()
        decision["seam_anchor_review_decision"]["review"]["notes"] = "tamper"
        attacks.append(decision)
        for values in attacks:
            with self.subTest(attack=attacks.index(values)), \
                    patch(PROOF_VALIDATOR, side_effect=fake_proof_sha), \
                    self.assertRaises(BodySwayDynamicSeamSourceError):
                build_body_sway_dynamic_seam_source(**values)

    def test_resealed_outer_identity_and_extra_fields_fail_replay(self):
        _values, source = self._build()
        identity = deepcopy(source)
        identity["seam_anchor_candidate_sha256"] = "f" * 64
        identity["source_set_sha256"] = (
            body_sway_dynamic_seam_source_sha256(identity)
        )
        extra = deepcopy(source)
        extra["latest"] = True
        extra["source_set_sha256"] = (
            body_sway_dynamic_seam_source_sha256(extra)
        )
        for attack in (identity, extra):
            with patch(PROOF_VALIDATOR, side_effect=fake_proof_sha), \
                    self.assertRaises(BodySwayDynamicSeamSourceError):
                require_body_sway_dynamic_seam_source(attack)

    def test_nonfinite_size_node_and_depth_budgets_fail_before_replay(self):
        nonfinite = build_kwargs()
        nonfinite["continuous_proof"]["nonfinite"] = float("nan")
        with self.assertRaises(BodySwayDynamicSeamSourceError):
            build_body_sway_dynamic_seam_source(**nonfinite)
        values = build_kwargs()
        with patch(
            "autospine_workbench.body_sway_dynamic_seam_source."
            "MAX_SEAM_CANDIDATE_BYTES", 1
        ), self.assertRaises(BodySwayDynamicSeamSourceError):
            build_body_sway_dynamic_seam_source(**values)
        with patch(
            "autospine_workbench.body_sway_dynamic_seam_source."
            "MAX_SOURCE_JSON_NODES", 2
        ), self.assertRaises(BodySwayDynamicSeamSourceError):
            build_body_sway_dynamic_seam_source(**build_kwargs())
        deep = build_kwargs()
        nested = cursor = {}
        for _index in range(170):
            cursor["x"] = {}
            cursor = cursor["x"]
        deep["continuous_proof"]["deep"] = nested
        with self.assertRaises(BodySwayDynamicSeamSourceError):
            build_body_sway_dynamic_seam_source(**deep)

    def test_deterministic_copy_isolated_and_zero_write(self):
        values = build_kwargs()
        original_project = values["continuous_proof"]["project_id"]
        with patch(PROOF_VALIDATOR, side_effect=fake_proof_sha), patch(
            "builtins.open", side_effect=AssertionError("write attempted")
        ):
            first = build_body_sway_dynamic_seam_source(**values)
            second = build_body_sway_dynamic_seam_source(**values)
        self.assertEqual(first, second)
        self.assertEqual(
            first["source_set_sha256"],
            body_sway_dynamic_seam_source_sha256(first),
        )
        self.assertNotEqual(canonical_sha256(first), first[
            "source_set_sha256"
        ])
        self.assertIn("dynamic-seam", SOURCE_HASH_DOMAIN)
        values["continuous_proof"]["project_id"] = "mutated"
        self.assertEqual(original_project, first[
            "body_sway_continuous_preview_proof"
        ]["project_id"])
        first["body_sway_continuous_preview_proof"]["project_id"] = "changed"
        self.assertEqual(original_project, second[
            "body_sway_continuous_preview_proof"
        ]["project_id"])
        self.assertFalse(any(key in first for key in (
            "analysis", "claims", "current_head", "latest", "path",
        )))


if __name__ == "__main__":
    unittest.main()
