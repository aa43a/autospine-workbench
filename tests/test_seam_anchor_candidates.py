"""P10.5a pure static seam candidate compiler tests."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from autospine_workbench.manifest_bundle import LayerManifestBundleReader
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.seam_anchor_candidate_profile import (
    GENERATOR,
    candidate_generator_profile,
)
from autospine_workbench.seam_anchor_candidate_validation import (
    seam_anchor_candidates_sha256,
)
from autospine_workbench.seam_anchor_runtime_guard import (
    SeamAnchorRuntimeProfileError,
)
from autospine_workbench.seam_anchor_candidates import (
    compile_seam_anchor_candidates,
)
from tests.p10_candidate_helpers import P10PersistedFixture
from tests.seam_anchor_candidate_helpers import seam_inputs


class SeamAnchorCandidateCompilerTests(unittest.TestCase):
    def test_generator_profile_seals_all_current_behavior_constants(self):
        generated = candidate_generator_profile()
        self.assertEqual(GENERATOR, generated)
        self.assertEqual(
            canonical_sha256(generated["algorithm_profile"]),
            generated["algorithm_profile_sha256"],
        )

    def test_exact_public_boundary_is_deterministic_and_clip_independent(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = P10PersistedFixture(Path(directory))
            manifest = LayerManifestBundleReader(fixture.state).load(
                fixture.mesh.project_id, fixture.layer_manifest_sha256
            ).manifest
            first = compile_seam_anchor_candidates(manifest, fixture.mesh)
            second = compile_seam_anchor_candidates(manifest, fixture.mesh)
        self.assertEqual(first, second)
        self.assertEqual(
            first.sha256, seam_anchor_candidates_sha256(first.document)
        )
        self.assertEqual(6, first.document["summary"]["relationship_count"])
        self.assertEqual(6, first.document["summary"]["unobservable_count"])
        self.assertFalse(any(
            token in key.casefold()
            for key in first.document["source"]
            for token in ("clip", "motion", "p10")
        ))

    def test_candidate_output_has_no_automatic_decision_or_release_claim(self):
        admitted = seam_inputs()
        with patch(
            "autospine_workbench.seam_anchor_candidates."
            "require_seam_anchor_inputs",
            return_value=admitted,
        ) as admission:
            compiled = compile_seam_anchor_candidates({}, object())
        admission.assert_called_once_with({}, unittest.mock.ANY)
        document = compiled.document
        self.assertEqual(6, document["summary"]["candidate_option_count"])
        self.assertEqual(24, document["summary"]["anchor_pair_count"])
        self.assertFalse(document["semantics"]["human_decision_emitted"])
        self.assertFalse(document["claims"]["dynamic_seam_safety"])
        self.assertFalse(document["claims"]["release_authority"])
        self.assertEqual("blocked", document["release_gate"]["status"])

    def test_generator_change_changes_hash_without_reusing_static_output(self):
        admitted = seam_inputs()
        target = "autospine_workbench.seam_anchor_candidates"
        with patch(f"{target}.require_seam_anchor_inputs",
                   return_value=admitted):
            baseline = compile_seam_anchor_candidates({}, object()).sha256
            with patch(
                "autospine_workbench.seam_anchor_candidate_profile."
                "CONTACT_MAX_GAP_PX", 9.0,
            ), patch(
                "autospine_workbench.seam_anchor_candidate_geometry."
                "CONTACT_MAX_GAP_PX", 9.0,
            ), patch(
                "autospine_workbench.seam_anchor_candidate_validation."
                "CONTACT_MAX_GAP_PX", 9.0,
            ):
                updated = compile_seam_anchor_candidates(
                    {}, object()
                ).sha256
        self.assertNotEqual(baseline, updated)

    def test_each_runtime_consumer_alias_fails_closed_when_unsynchronized(self):
        cases = (
            ("seam_anchor_candidate_validation", "MAX_DOCUMENT_BYTES", 1),
            ("seam_anchor_candidate_validation", "MAX_OPTIONS_PER_RELATION", 1),
            ("seam_anchor_candidate_validation", "MAX_TOTAL_OPTIONS", 1),
            ("seam_anchor_candidate_validation", "MAX_ANCHOR_PAIRS", 7),
            ("seam_anchor_candidate_validation", "CONTACT_MAX_GAP_PX", 7.0),
            ("seam_anchor_candidate_validation", "RELATIONSHIP_PROFILE", ()),
            ("seam_anchor_candidate_validation", "FORMAT", "changed"),
            ("seam_anchor_candidate_validation", "FORMAT_VERSION", 2),
            ("seam_anchor_candidate_validation", "SEMANTICS", {}),
            ("seam_anchor_candidate_validation", "CLAIMS", {}),
            ("seam_anchor_candidate_validation", "RELEASE_GATE", {}),
            ("seam_anchor_candidate_validation",
             "SEAM_SOURCE_IDENTITY_FIELDS", ()),
            ("seam_anchor_candidates", "FORMAT", "changed"),
            ("seam_anchor_candidates", "FORMAT_VERSION", 2),
            ("seam_anchor_candidates", "SEMANTICS", {}),
            ("seam_anchor_candidates", "CLAIMS", {}),
            ("seam_anchor_candidates", "RELEASE_GATE", {}),
            ("seam_anchor_candidate_fields", "REGION_QUANTIZATION", 4095),
            ("seam_anchor_candidate_fields", "MESH_QUANTIZATION", 65534),
            ("seam_anchor_candidate_fields", "MAX_MESH_VERTICES", 4095),
            ("seam_anchor_candidate_fields", "MAX_MESH_TRIANGLES", 8191),
            ("seam_anchor_candidate_fields",
             "MAX_ABS_ATTACHMENT_COORDINATE", 999_999_999),
            ("seam_anchor_candidate_fields", "MAX_ATTACHMENT_PIXELS", 1),
            ("seam_anchor_candidate_policy", "MIN_ANCHOR_PAIRS", 3),
            ("seam_anchor_relations", "_VALID_SIDES", frozenset()),
        )
        prefix = "autospine_workbench."
        for module, attribute, value in cases:
            with self.subTest(module=module, attribute=attribute), patch(
                f"{prefix}{module}.{attribute}", value,
            ):
                with self.assertRaises(SeamAnchorRuntimeProfileError):
                    candidate_generator_profile()

    def test_duplicate_role_token_rows_fail_closed(self):
        from autospine_workbench import seam_anchor_relations as relations

        duplicate = (("arm", ("extra",)), *relations.ROLE_TOKEN_PROFILE)
        with patch.object(relations, "ROLE_TOKEN_PROFILE", duplicate):
            with self.assertRaises(SeamAnchorRuntimeProfileError):
                candidate_generator_profile()

    def test_compiler_checks_runtime_before_admitting_or_decoding_inputs(self):
        target = "autospine_workbench.seam_anchor_candidates"
        with patch(
            f"{target}.require_candidate_runtime_consistency",
            side_effect=SeamAnchorRuntimeProfileError("diverged"),
        ) as guard, patch(f"{target}.require_seam_anchor_inputs") as admission:
            with self.assertRaisesRegex(Exception, "compilation failed"):
                compile_seam_anchor_candidates({}, object())
        guard.assert_called_once_with()
        admission.assert_not_called()

    def test_absence_reason_policy_changes_generator_identity(self):
        from autospine_workbench import seam_anchor_candidate_policy as policy

        baseline = candidate_generator_profile()["algorithm_profile_sha256"]
        changed = policy.ABSENCE_REASON_CODES - {"PARENT_ROLE_MISSING"}
        with patch.object(policy, "ABSENCE_REASON_CODES", changed):
            updated = candidate_generator_profile()[
                "algorithm_profile_sha256"
            ]
        self.assertNotEqual(baseline, updated)


if __name__ == "__main__":
    unittest.main()
