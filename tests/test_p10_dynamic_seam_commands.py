"""Orchestration, concurrency, input, and zero-write tests for P10.5d."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for item in (ROOT, SRC):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from autospine_workbench.p10_dynamic_seam_commands import (  # noqa: E402
    P10DynamicSeamCommandError,
    compile_body_sway_dynamic_seam_probe_command,
)
from tests.p10_dynamic_seam_command_helpers import (  # noqa: E402
    SHAS,
    observation,
    patched_command_pipeline,
    proof_document,
    write_proof,
)
from tests.p9_v2_helpers import tree  # noqa: E402


def compile_at(root: Path, proof_path: Path):
    return compile_body_sway_dynamic_seam_probe_command(
        root,
        "fixture-project",
        proof_path,
        reviewed_set_sha256=SHAS[1],
        reviewed_set_bundle_sha256=SHAS[2],
    )


class P10DynamicSeamCommandTests(unittest.TestCase):
    def test_exact_order_double_check_output_and_zero_write(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            proof_path = write_proof(root)
            before_tree = tree(root)
            with patched_command_pipeline() as fixture:
                result = compile_at(root, proof_path)
            after_tree = tree(root)
        self.assertEqual(before_tree, after_tree)
        self.assertEqual(
            [
                "proof", "bundle", "source", "head", "compile", "head",
                "validate", "probe-hash",
            ],
            fixture.order,
        )
        document = result.document
        self.assertEqual(fixture.probe.document, document["probe"])
        self.assertEqual(SHAS[4], document[
            "body_sway_dynamic_seam_probe_sha256"
        ])
        head = document["head_observation"]
        self.assertEqual(
            "outer-before-after-analysis-of-inner-double-snapshots",
            head["method"],
        )
        self.assertEqual("compile_time", head["scope"])
        self.assertFalse(head["permanent_authority_claimed"])
        self.assertEqual("exact_match", head["checks"][
            "before_after_identity"
        ])
        encoded = str(document)
        self.assertNotIn(str(root), encoded)
        self.assertNotIn("continuous-proof.json", encoded)

    def test_exact_addresses_and_documents_feed_source_closure(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            proof_path = write_proof(root)
            with patched_command_pipeline() as fixture:
                compile_at(root, proof_path)
        fixture.reader_class.assert_called_once_with(root)
        fixture.reader_class.return_value.load.assert_called_once_with(
            "fixture-project", SHAS[1], SHAS[2]
        )
        fixture.source_builder.assert_called_once_with(
            continuous_proof=proof_document(),
            seam_anchor_candidates=fixture.bundle.candidates,
            seam_anchor_review_decision=fixture.bundle.decision,
            reviewed_seam_anchor_set=fixture.bundle.reviewed_set,
            reviewed_set_bundle_sha256=SHAS[2],
        )
        self.assertEqual(2, fixture.head_check.call_count)
        fixture.compiler.assert_called_once()
        fixture.validator.assert_called_once_with(fixture.probe.document)

    def test_identity_or_canonical_head_change_fails_before_validation(self):
        attacks = (
            (observation(identity="before"), observation(identity="after")),
            (observation(marker="before"), observation(marker="after")),
        )
        for before, after in attacks:
            with self.subTest(attack=before.identity), \
                    tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                proof_path = write_proof(root)
                with patched_command_pipeline(
                    before=before, after=after
                ) as fixture, self.assertRaises(
                    P10DynamicSeamCommandError
                ):
                    compile_at(root, proof_path)
                fixture.validator.assert_not_called()
                fixture.probe_hash.assert_not_called()

    def test_full_proof_source_and_public_validation_fail_closed(self):
        failures = (
            {"proof_failure": ValueError("private proof failure")},
            {"source_failure": ValueError("private source failure")},
            {"validator_failure": ValueError("private validator failure")},
        )
        for options in failures:
            with self.subTest(options=tuple(options)), \
                    tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                proof_path = write_proof(root)
                with patched_command_pipeline(**options), self.assertRaises(
                    P10DynamicSeamCommandError
                ) as raised:
                    compile_at(root, proof_path)
                self.assertEqual(
                    "Body-sway dynamic seam probe compilation failed",
                    str(raised.exception),
                )

    def test_bounded_strict_input_fails_before_historical_load(self):
        invalid = (
            '{"project_id":"fixture-project","project_id":"again"}',
            '{"project_id":"fixture-project","bad":NaN}',
            "[]",
        )
        for raw in invalid:
            with self.subTest(raw=raw), \
                    tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                proof_path = write_proof(root, raw=raw)
                with patched_command_pipeline() as fixture, \
                        self.assertRaises(P10DynamicSeamCommandError):
                    compile_at(root, proof_path)
                fixture.proof_hash.assert_not_called()
                fixture.reader_class.return_value.load.assert_not_called()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            proof_path = write_proof(root)
            with patch(
                "autospine_workbench.p10_dynamic_seam_commands."
                "MAX_CONTINUOUS_PROOF_BYTES",
                1,
            ), patched_command_pipeline() as fixture, self.assertRaises(
                P10DynamicSeamCommandError
            ):
                compile_at(root, proof_path)
            fixture.proof_hash.assert_not_called()

    def test_result_is_copy_isolated_and_bundle_address_is_rechecked(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            proof_path = write_proof(root)
            with patched_command_pipeline() as fixture:
                result = compile_at(root, proof_path)
            first = result.document
            first["probe"]["status"] = "forged"
            self.assertEqual("fixture-status", result.document[
                "probe"
            ]["status"])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            proof_path = write_proof(root)
            with patched_command_pipeline() as fixture:
                fixture.bundle.set_sha256 = "f" * 64
                with self.assertRaisesRegex(
                    P10DynamicSeamCommandError, "explicit address"
                ):
                    compile_at(root, proof_path)

    def test_command_source_has_no_discovery_or_mutation_boundary(self):
        source = (SRC / "autospine_workbench" /
                  "p10_dynamic_seam_commands.py").read_text(encoding="utf-8")
        for forbidden in (
            ".glob(", ".rglob(", "publish_", "write_", "mkdir(",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
